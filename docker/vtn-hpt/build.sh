# Retrieve path to directory containing this script. 
CONFIG_SCRIPT_DIR="$(dirname $(readlink -f $0))"

# Build the image.
# docker build --no-cache -t openleadr-vtn ${CONFIG_SCRIPT_DIR}
docker build $@ -t openleadr-vtn ${CONFIG_SCRIPT_DIR}
