FROM python:3.10

# Create user
RUN useradd -m jupyter
EXPOSE 8100

RUN apt update && apt install -y lsof

# Install uv (faster than pip, matches apptainer)
RUN pip install --no-cache-dir uv

# Install hatch using uv
RUN uv pip install --system --no-cache hatch

# Copy project files
COPY --chown=1000:1000 . /jupyter/
RUN chown -R 1000:1000 /jupyter

# Install package using uv (matches jupyter.def)
RUN uv pip install --system --no-cache -e /jupyter

# Set environment
ENV PYTHONPATH=/jupyter
ENV PORT=8100

# Switch to non-root user
USER jupyter
WORKDIR /jupyter

# Service - use beaker dev watch (matches apptainer)
CMD ["sh", "-c", "beaker dev watch --ip 0.0.0.0 --port $PORT"]
