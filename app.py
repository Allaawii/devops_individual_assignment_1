"""Entry point: python app.py"""

from trainer import create_app

app = create_app()

if __name__ == "__main__":
    config = app.config["APP_CONFIG"]
    app.run(host="0.0.0.0", port=config.port, debug=False)
