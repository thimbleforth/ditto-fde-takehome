# ditto-fde-takehome
This is my repo for Ditto's FDE take-home exam.

## Features
### Functional Requirements:
✅ Multiple edge locations can create and update reports

✅ Changes sync automatically to a central government cloud database (PostgreSQL in AWS RDS)

✅ Handles conflicting updates (e.g., two analysts update the same report offline)

✅ Display sync status and conflict resolution

✅ Support audit logging (who, what, when for compliance)

### Technical Requirements:
✅ Use any language/framework you're comfortable with: Python, SQLite for local storage, Flask to simulate a small / serverless cloud server. Database is accessible through a small API, and only after jwt-based authentication.

✅ Implement or simulate a sync mechanism between edge and cloud: multiple containers in a network sync data to a central cloud.

✅ Include conflict resolution logic appropriate for collaborative work

✅ Add comments explaining your design decisions

✅ Consider idempotency and retry logic

✅ Demonstrate security considerations (authentication, encryption in transit

## How to Run

1. Generate the ssl keys: 
```bash
mkdir ./edge/keys && cd ./edge/keys
openssl genrsa -out private.pem 2048
openssl rsa -in private.pem -pubout -out public.pem
```
If you're on Windows just use WSL2. `wsl` at the CLI, do the above, `exit`, et voila.

2. Run the `docker-compose.yml` at the root of the repo. That will spawn up both the edge and cloud docker containers for a quick simulation of the edge sync functionality. It will import the keys you just generated in order to handle the jwt auth.

3. Once the containers are up, you'll be able to hit the Flask instance on the `cloud_app` container on `localhost:8443`. From there you'll be able to see the full cloud db's data and sync status in a small HTML page.

4. Click the `Get Latest Reports` button to show the latest reports of a given ID. If you want to validate that a specific ID has had multiple updates, use the report ID `shared-report-050`. I've hard coded that to occur multiple times to demonstrate multiple sync attempts. You can CTRL-F and view both in the `Get Reports` section. Compare that, with the single remaining result in `Get Latest Reports` under that `report_id`.

Optional: You can also hit the `/api/health` and `/api/reports` endpoints directly to see the JSON yourself and ensure that those routes are working.

## Sync Strategy
The sync strategy is "last write wins," plain and simple. The format of the reports is simple enough that the DB can take in changes on a given ID without a lot of fuss.

Currently, the database records all of the changes, assigning a unique ID. So the latest ID (ergo, latest recorded change) of a given record_id, is what's shown when you click `Get Latest Reports`.

## Tradeoffs / CAP Theorem
The system as currently designed is meant to run solely in containers, and is set up as a "client-server" system for ease of implementation.

Meaning that you always have Availability, locally; and you can always tolerate Partitions, but you're not always going to be Consistent - hence the syncing mechanism.

In the real world, the edge_app and cloud_app functionality would be rolled into a single agent so you aren't worried about local network stuff within a given k8s cluster or Docker Swarm onboard a device.

## Scalability
This setup could scale to 100+ edge locations **after** hops / distance relationships between nodes was implemented. This would help keep the burden of individual reports smaller on individual devices, while allowing not only edge-to-cloud, but edge-to-edge synchronization.

In the event E2E sync was not in the cards, E2C sync is achievable with an Application Load Balancer and possibly a durable Lambda setup.

Cloud endpoint storage is a non-issue, it's as hardened and as expandable as you want. I'd use S3 for the cloud storage component.

## Cloud deployment considerations
In the event this was deployed in AWS or Azure, slight refactors to `cloud_app.py` could render it usable as a serverless Lambda/Azure Functions application, thus making it much more scalable per the above.

I'd also focus on using AWS Security Hub and declarative compliance controls at the cloud layer, since that attack surface is a lot wider than any individual instance of the software itself.

## Security and compliance considerations
* The edge and cloud apps use FIPS-compliant RSA2048 keys for the JWT token exchanges.

* The containers all run as non-root users.

* Versions in each `requirements.txt` are pinned, instead of using the latest version.

* Same goes for the Dockerfiles; version of the Python image is pinned.

* This POC does not use HTTPS or a production-ready WSGI server. Both of those problems would have to be fixed at minimum to improve this software's production readiness.
