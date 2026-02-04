.PHONY: up down logs migrate superuser test shell collectstatic clean restart test-coverage test-local test-local-coverage

# Build and start all services
up:
	docker-compose up -d --build

# Stop and remove containers
down:
	docker-compose down

# Tail logs for all services
logs:
	docker-compose logs -f

# Run database migrations
migrate:
	docker-compose exec web python manage.py migrate

# Create a Django superuser
superuser:
	docker-compose exec web python manage.py createsuperuser

# Run the test suite
test:
	docker-compose exec web pytest

# Run tests with coverage report (Docker)
test-coverage:
	docker-compose exec web pytest --cov=core --cov-report=term-missing --cov-report=html

# Run tests locally (no Docker)
test-local:
	pytest tests/

# Run tests locally with coverage
test-local-coverage:
	pytest tests/ --cov=core --cov-report=term-missing --cov-report=html --tb=short

# Open Django shell
shell:
	docker-compose exec web python manage.py shell

# Collect static files
collectstatic:
	docker-compose exec web python manage.py collectstatic --noinput

# Clean up containers, volumes, and orphans
clean:
	docker-compose down -v --remove-orphans

# Restart all services
restart: down up

# Full rebuild with static files
rebuild:
	docker-compose down
	docker-compose up -d --build
	docker-compose exec web python manage.py collectstatic --noinput
	docker-compose exec web python manage.py migrate
