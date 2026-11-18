// Where the two services are. This committed file is the local default (docker compose, or
// python app.py on these ports). The deploy job overwrites it with the Azure Container Apps URLs.
window.FRASE_CONFIG = {
  contentUrl: "http://localhost:8001",
  schedulerUrl: "http://localhost:8002",
};
