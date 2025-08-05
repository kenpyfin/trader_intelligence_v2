# Architecture and Development Plan

This document outlines a recommended architecture and development plan for the "Trader Intelligence" application, as described in `pdr.md`. The plan is designed to be both scalable for future growth and lean for rapid initial development, leveraging the existing components in the codebase.

## 1. High-Level Architecture

The proposed architecture is a modern, containerized web application with a decoupled frontend and backend. This approach provides clear separation of concerns, allows for independent development and scaling of services, and aligns with the provided `docker-compose_example.yml`.

- **Frontend:** A Single-Page Application (SPA) built with a modern JavaScript framework like **React**. This will provide a rich, interactive, and responsive user experience. The existing `frontend/Dockerfile` and `nginx.conf` provide a production-ready setup for this.
- **Backend:** A high-performance asynchronous API service built with **Python/FastAPI**. FastAPI is an excellent choice due to its speed, automatic API documentation, and strong async support, which is critical for handling I/O-heavy operations like fetching data from external APIs and interacting with the database. The existing `backend/Dockerfile` already sets this up.
- **Database:** **MongoDB** will be used as the primary database, as suggested in the project's configuration files. Its flexible, document-based nature is well-suited for storing varied data such as user portfolios, trade history, and cached market analysis.
- **Broker Integration:** An interface to the Interactive Brokers API, encapsulated within a dedicated module in the backend. The existing `my_libs_py3/TD_Order.py` (`IBTrader` class) serves as the foundation for this.
- **Containerization:** All services will be containerized using **Docker** and orchestrated for local development with **Docker Compose**, following the pattern in `docker-compose_example.yml`.

### Architecture Diagram

```
+----------------+      +---------------------+      +----------------------+
|                |      |                     |      |                      |
|  React Client  |----->|     Nginx Proxy     |----->|   FastAPI Backend    |
| (Browser)      |      | (Serves React App & |      |   (Python Service)   |
|                |      |   Proxies API)      |      |                      |
+----------------+      +---------------------+      +----------+-----------+
                                                                  |
                                          +-----------------------+-----------------------+
                                          |                       |                       |
                                   +------v------+         +------v------+         +------v------+
                                   |             |         |             |         |             |
                                   |  MongoDB    |         | Finviz/FMP  |         | Interactive |
                                   | (Database)  |         |   APIs      |         |   Brokers   |
                                   |             |         |             |         |             |
                                   +-------------+         +-------------+         +-------------+
```

### 1.1. Deployment Strategy: Why Docker?

Using **Docker** and **Docker Compose**, as established in the project's example files, is the ideal deployment strategy for this application. It is not just a viable option but a best practice for modern web development.

-   **Consistency:** Docker containers package the application and its dependencies together, ensuring that the software runs the same way in development, testing, and production environments. This eliminates the common "it works on my machine" problem.
-   **Isolation:** The frontend (Node.js/React) and backend (Python/FastAPI) services run in separate, isolated containers. This prevents dependency conflicts and allows them to be developed, updated, and scaled independently.
-   **Portability & Scalability:** A containerized application can run on any system that supports Docker, from a developer's laptop to a cloud provider (AWS, GCP, Azure). While `docker-compose` is excellent for single-host development, the same Docker images can be deployed to powerful orchestration platforms like Kubernetes for automated scaling and high availability.
-   **Simplified Setup:** For new developers, the setup process is reduced to installing Docker and running a single command (`docker-compose up`). There is no need to manually install and configure Python, Node.js, databases, or web servers.

#### Alternatives Considered

-   **Platform-as-a-Service (PaaS) (e.g., Heroku, Render):** PaaS solutions are easier to start with but offer less control and can become more expensive at scale. Many modern PaaS providers now deploy applications from Dockerfiles, making Docker a foundational skill even in that context.
-   **Bare-Metal/VM Deployment:** Manually installing and managing all software components on a server is complex, error-prone, and difficult to reproduce consistently. This approach does not scale well and is not recommended for a multi-service application.

For these reasons, this plan will proceed with the established container-based strategy.

## 2. Refactoring `option_trade.py`

The existing Streamlit application (`option_trade.py`) contains the core business logic. For a scalable application, this logic must be decoupled from the UI.

- **Analysis Logic:** Functions like `universal_binomial_pricer`, `analyze_...`, and `generate_holistic_conclusion` should be moved into an `analytics` module within the FastAPI backend.
- **Data Fetching:** The `PriceDataFetcher` class should be integrated directly into the backend to supply data to the analysis module.
- **Broker Interaction:** The `IBTrader` class should be part of a `broker` module in the backend, handling all communication with Interactive Brokers.
- **API Endpoints:** The backend will expose this logic through RESTful API endpoints, such as:
    - ✅ `POST /api/analyze/stock`: Takes a ticker and parameters, returns a full analysis.
    - `GET /api/portfolio`: Returns the user's tracked positions.
    - `POST /api/portfolio/positions`: Adds a new position.
    - ✅ `POST /api/orders/strategy`: Places a complex strategy order via the broker.

## 3. Lean Development Plan

This plan breaks down the project into iterative phases, delivering value quickly and building upon a solid foundation.

### Phase 1: Foundation & Core Logic Migration (MVP Backend) - Complete
*   **Goal:** Validate the end-to-end architecture with core functionality.
*   **Tasks:**
    1.  ✅ Set up the repository with the `frontend` and `backend` directories.
    2.  ✅ Implement the basic FastAPI backend service based on the `backend/Dockerfile`.
    3.  ✅ Migrate the core analysis and pricing models from `option_trade.py` into a backend `analytics` module.
    4.  ✅ Integrate `PriceDataFetcher` into the backend to fetch data from FMP/Finviz.
    5.  ✅ Create a single API endpoint (`POST /api/analyze/stock`) that runs the analysis and returns the result as JSON.
    6.  ✅ Develop a rich React frontend to call the analysis endpoint and display the results in a structured, user-friendly dashboard.
    7.  ✅ Use Docker Compose to run all services locally.


### Phase 2: Broker Integration & Live Trading - In Progress
*   **Goal:** Enable trade execution from the application.
*   **Tasks:**
    1.  ✅ Integrate the `IBTrader` class into a backend `broker` service.
    2.  ✅ Create a backend API endpoint (`POST /api/orders/strategy`) for placing complex strategy orders.
    3.  ✅ Build a UI component in the frontend for executing the recommended strategy with a single click.
    4.  ✅ Display immediate order submission status to the user.
    5.  Implement a mechanism to query and display live/filled order statuses continuously.
    6.  Add UI for canceling open orders.

### Phase 3: Scalability and Advanced Features
*   **Goal:** Enhance performance, reliability, and feature set.
*   **Tasks:**
    1.  Introduce a dedicated caching layer (e.g., Redis) for expensive API calls and frequently accessed data to reduce latency and cost.
    2.  Implement background workers (e.g., using Celery) for long-running tasks like fetching large historical datasets or performing nightly portfolio risk analysis.
    3.  Develop the portfolio risk management features outlined in `pdr.md`.
    4.  Improve monitoring, logging, and alerting for all services.
