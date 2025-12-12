"""
Flask webhook server for receiving Twilio SMS messages.
Runs in background thread to handle incoming verification codes.
"""

import os
import threading
from typing import Optional
from flask import Flask, request


class WebhookServer:
    """
    Flask-based webhook server for receiving Twilio SMS messages.
    Runs in a background daemon thread.
    """

    def __init__(self, twilio_service):
        """
        Initialize webhook server.

        Args:
            twilio_service: TwilioService instance for message storage
        """
        self.twilio_service = twilio_service
        self.port = int(os.getenv("WEBHOOK_PORT", "5000"))
        self.app = Flask(__name__)
        self.server_thread: Optional[threading.Thread] = None
        self.is_running = False

        self._setup_routes()

    def _setup_routes(self):
        """
        Configure Flask routes for webhook endpoints.
        """

        @self.app.route("/sms", methods=["POST"])
        def sms_webhook():
            """
            Handle incoming SMS from Twilio.
            Twilio sends POST request with form data.
            """
            try:
                from ..utils.ui import dashboard

                from_number = request.form.get("From", "")
                to_number = request.form.get("To", "")
                body = request.form.get("Body", "")

                dashboard.add_webhook_event(
                    "SMS",
                    from_number[-4:] if from_number else "Unknown",
                    body[:40] if body else "Empty message",
                )

                if body:
                    self.twilio_service.store_message(from_number, to_number, body)

                return (
                    '<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                    200,
                )

            except Exception as e:
                from ..utils.ui import dashboard

                dashboard.add_webhook_event("ERROR", "Webhook", str(e)[:40])
                return f"Error: {str(e)}", 500

        @self.app.route("/health", methods=["GET"])
        def health_check():
            """
            Health check endpoint.
            """
            return {"status": "ok", "service": "twilio-webhook"}, 200

    def start(self):
        """
        Start webhook server in background thread.
        Automatically finds available port if default is in use.
        """
        if self.is_running:
            return

        self.is_running = True

        def run_server():
            """
            Run Flask server with minimal logging.
            """
            import socket

            from computer_use.utils.logging_config import silence_flask_logs

            silence_flask_logs()

            import click

            click.echo = lambda *args, **kwargs: None
            click.secho = lambda *args, **kwargs: None

            max_attempts = 10

            for attempt in range(max_attempts):
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.bind(("0.0.0.0", self.port))

                    self.app.run(
                        host="0.0.0.0",
                        port=self.port,
                        debug=False,
                        use_reloader=False,
                    )
                    break

                except OSError:
                    if attempt < max_attempts - 1:
                        self.port += 1
                    else:
                        self.is_running = False
                        raise

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()

        import time

        time.sleep(0.3)

    def stop(self):
        """
        Stop webhook server.
        Note: Flask doesn't support graceful shutdown easily.
        Server will stop when main program exits (daemon thread).
        """
        self.is_running = False

    def get_webhook_url(self, use_ngrok: bool = False) -> Optional[str]:
        """
        Get webhook URL for Twilio configuration.

        Args:
            use_ngrok: Whether to use ngrok for public URL

        Returns:
            Webhook URL or None if unavailable
        """
        if use_ngrok:
            return self._get_ngrok_url()

        return f"http://localhost:{self.port}/sms"

    def _get_ngrok_url(self) -> Optional[str]:
        """
        Get ngrok public URL if available.

        Returns:
            Ngrok public URL or None
        """
        try:
            from pyngrok import ngrok

            ngrok_auth_token = os.getenv("NGROK_AUTH_TOKEN")
            if ngrok_auth_token:
                ngrok.set_auth_token(ngrok_auth_token)

            public_url = ngrok.connect(self.port)
            return f"{public_url}/sms"

        except Exception:
            return None
