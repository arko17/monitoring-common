FROM python:3.13-slim
RUN pip install --no-cache-dir --root-user-action=ignore rctclient==0.0.6
COPY exporter.py /exporter.py
USER 65534
EXPOSE 9894
CMD ["python", "-u", "/exporter.py"]
