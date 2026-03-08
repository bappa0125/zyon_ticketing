# Project Structure

```
zyon_ai_ticketing/
├── config/
│   ├── dev.yaml          # Development config
│   └── prod.yaml         # Production config
├── docker/
│   └── nginx.conf        # Nginx reverse proxy config
├── docs/
│   ├── ARCHITECTURE.md
│   └── PROJECT_STRUCTURE.md
├── frontend/             # Next.js chat UI
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   └── lib/
│   ├── package.json
│   └── Dockerfile
├── backend/              # FastAPI
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── api/
│   │   ├── core/
│   │   ├── models/
│   │   └── services/
│   ├── requirements.txt
│   └── Dockerfile
├── .github/
│   └── workflows/
│       └── ci-cd.yml
├── docker-compose.yml
└── README.md
```
