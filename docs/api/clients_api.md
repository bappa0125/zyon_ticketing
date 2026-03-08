# Clients API

## GET /api/clients

Returns monitored clients with domain and competitors.

### Example Request

```http
GET /api/clients HTTP/1.1
Host: localhost
```

### Example Response

```json
{
  "clients": [
    {
      "name": "Sahi",
      "domain": "sahi.com",
      "competitors": ["Zerodha", "Upstox", "Groww"]
    }
  ]
}
```

### Performance Notes

- Results cached in Redis under key `clients_config`
- TTL: 300 seconds
- File `config/clients.yaml` is read only on cache miss
- Minimal memory usage
