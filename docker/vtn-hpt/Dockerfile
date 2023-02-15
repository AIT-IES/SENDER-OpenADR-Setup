FROM ubuntu

WORKDIR /usr/app

RUN apt-get update && apt-get -y install python3 python3-pip git

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

COPY vtn_hpt.py ./
CMD [ "python3", "./vtn_hpt.py" ]
