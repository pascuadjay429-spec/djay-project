FROM python:3.12-slim
WORKDIR /app
COPY sg_shared.py storm_router_site.py storm_panel_site.py storm_web.py ./
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
# Render sets PORT
EXPOSE 8080
CMD ["python", "storm_web.py"]
