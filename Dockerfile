FROM plus3it/tardigrade-ci:0.26.2

COPY ./src/requirements.txt /app/requirements/lambda.txt

RUN python -m pip install --no-cache-dir \
    -r /app/requirements/lambda.txt
