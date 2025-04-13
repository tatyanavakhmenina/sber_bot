FROM python:3.12.10-slim-bullseye

COPY * /

RUN pip install -r requirements.txt

ENTRYPOINT [ "python" ]

CMD [ "labor_code_bot.py" ]