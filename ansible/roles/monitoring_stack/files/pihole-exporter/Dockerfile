FROM python:3.13-slim
COPY exporter.py /exporter.py
USER 65534
EXPOSE 9617
CMD ["python", "-u", "/exporter.py"]
