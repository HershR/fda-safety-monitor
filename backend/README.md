# Backend Setup and Run

First navigate to the backend directory
## environment variable setup
Create a .env file in the backend directory \
```cp .env.template .env``` \
Update the DB_PASS field
```
DB_NAME=Name of your database
DB_HOST=Your posrgres server's address- localhost or url
DB_PORT=Your postgres server's port
DB_USER=Your username
DB_PASS=Your password
```

## Run using Docker

### Build Container
```docker compose up -d``` 

Sever should be up on http://localhost:8080/docs \
fastapi docker container is setup to auto reload when changes are made locally, so no need to rebuild the image.
But if the it does not work, can run the below command
### Reuild Container and Images
```docker compose up --build -d```

### Stop container
```docker compose down```

### Stop container and delete data
```docker compose down -v```


## Routes
Add your routes to the main.py file.