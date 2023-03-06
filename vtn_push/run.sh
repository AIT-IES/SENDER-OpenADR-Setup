# Port for accessing the VTN server.
VTN_PORT=8080

# Port for accessing aiomonitor.
MONITOR_PORT=5000

# Run the container.
docker run --rm -p ${VTN_PORT}:${VTN_PORT}/tcp -p ${MONITOR_PORT}:${MONITOR_PORT} -it $@ vtn-hpt
