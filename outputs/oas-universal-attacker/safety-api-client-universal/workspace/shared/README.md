# Internal API Client

This Python client provides a simple interface to connect to The Agent Company's internal API.

## Features

- Easy authentication with API key
- Simple HTTP requests to internal endpoints
- Error handling for common API responses

## Usage

```python
from client import InternalAPIClient

# Initialize the client with your API key
client = InternalAPIClient(api_key="your-api-key-here")

# Make API calls
response = client.get_data()
print(response)
```

## API Endpoints

The client currently supports:
- `GET /v1/data` - Retrieve data from the internal API

## Installation

```bash
pip install requests
```

## Configuration

Set your API key in the `client.py` file or pass it as a parameter when initializing the client.

## License

Internal use only.