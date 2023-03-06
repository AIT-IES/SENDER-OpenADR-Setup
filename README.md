# SENDER OpenADR Setup

## About

This repository provides the [VTN](https://www.openadr.org/faq#17) setup for SENDER Task 6.4 (Functional Testing).

+ VTN server in POLL MODE (connection between TRIALOG and AIT)
+ VTN server in PUSH MODE (connection between HPT and AIT)
+ clients for retrieving flexibility offers from TRIALOG and HPT
+ time series database for storing sent events and received reports (using [Prometheus](https://prometheus.io))
+ dashboard for visualizing sent events and received reports (using [Grafana](https://grafana.com)) 
+ back-up database for registered [VEN](https://www.openadr.org/faq#18) clients (using [Redis](https://redis.io))

All components of this setup are run in [Docker containers](https://www.docker.com/resources/what-container/), deployed with the help of [Docker Compose](https://docs.docker.com/compose/).
Network acces to the containers is handled via a reverse proxy (using [Traefik](https://traefik.io/)).

## Usage

### Hostname

The hostname is defined via environment variable `HOST` in file `.env`.
The setup is intended to run on the *VLab Central* server (vlab-central.ait.ac.at).
For testing, the host name can be simply changed to `localhost`.

### Deployment of the setup

Use the [Docker Compose CLI](https://docs.docker.com/compose/reference/) for deployment of the setup.

+ deploy complete steup:
  ```shell
  docker compose --profile all up 
  ```
+ deploy TRIALOG-AIT setup only:
  ```shell
  docker compose --profile trialog up 
  ```
+ deploy HPT-AIT setup only:
  ```shell
  docker compose --profile hpt up 
  ```

### Interacting with the VTN server

By default, the VTN endpoints are:

+ POLL MODE VTN / TRIALOG-AIT setup: `https://<HOST_NAME>:8080/Test-TRIALOG-AIT/OpenADR2/Simple/2.0b`
+ PUSH MODE VTN / HPT-AIT setup: `https://<HOST_NAME>:8080/Test-HPT-AIT/OpenADR2/Simple/2.0b`

You can interact with both VTN servers from a Python command prompt:
```python
>>> from vtn_common.vtn_terminal import *
>>> start_terminal(5001)
>>> ps()
+-----------------+---------+-----------------------------------------------------------------------+
| Task ID         | State   | Task                                                                  |
+-----------------+---------+-----------------------------------------------------------------------+
| 139859962624288 | PENDING | <Task pending name='Task-1' coro=<VTNMonitor._heart_beat() running at |
|                 |         | /usr/app/vtn_common/vtn_monitor.py:48> wait_for=<Future pending       |
|                 |         | cb=[Task.task_wakeup()]>>                                             |
+-----------------+---------+-----------------------------------------------------------------------+
>>> add_single_event('VEN_ID_Trialog_VEN')
```

### Accessing the dashboard / time series database

The Prometheus time series database is available on port 9090.

The Grafana dashboard is available on port 3000.

## Testing

+ For testing, the host name can be changed to `localhost` in file `.env`.
+ Simple VEN clients for testing are available in sub-folder `test`.
  ```shell
  pip install -r test/requirements_testing.txt
  python test/ven_trialog_test.py
  ```
+ Access the Grafana dashboard via http://localhost:3000


