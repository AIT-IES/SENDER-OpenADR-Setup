FROM ubuntu

WORKDIR /usr/app

RUN apt-get update && apt-get -y install python3 python3-pip git

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

COPY flex_trialog.py ./
CMD [ "python3", "./flex_trialog.py" ]
