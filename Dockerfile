FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get -qq update --fix-missing && apt-get -qq upgrade -y && apt-get install git -y

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["bash","start.sh"]
