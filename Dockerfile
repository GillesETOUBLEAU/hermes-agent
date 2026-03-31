FROM debian:13.4

LABEL maintainer="GillesETOUBLEAU"
LABEL railway.deploy="true"

RUN apt-get update
RUN apt-get install -y nodejs npm python3 python3-pip ripgrep ffmpeg gcc python3-dev libffi-dev

COPY . /opt/hermes
WORKDIR /opt/hermes

RUN pip install -e ".[all]" --break-system-packages
RUN pip install google-api-python-client google-auth-oauthlib google-auth-httplib2 --break-system-packages
RUN npm install
RUN npm install -g @googleworkspace/cli
RUN npx playwright install --with-deps chromium
WORKDIR /opt/hermes/scripts/whatsapp-bridge
RUN npm install

WORKDIR /opt/hermes
RUN chmod +x /opt/hermes/docker/entrypoint.sh

ENV HERMES_HOME=/opt/data
ENV PYTHONUNBUFFERED=1
ENTRYPOINT [ "/opt/hermes/docker/entrypoint.sh" ]