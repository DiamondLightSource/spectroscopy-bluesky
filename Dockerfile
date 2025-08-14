# The devcontainer should use the developer target and run as root with podman
# or docker with user namespaces.
ARG PYTHON_VERSION=3.13@sha256:1e4584c017d9cecf8a952cfd8f8e47ef5611b28dfc29da9e1d4b6bad98daf9b0
FROM python:${PYTHON_VERSION} AS developer

# Add any system dependencies for the developer/build environment here
RUN apt-get update && apt-get install -y --no-install-recommends \
    graphviz \
    && rm -rf /var/lib/apt/lists/*

# Set up a virtual environment and put it in PATH
RUN python -m venv /venv
ENV PATH=/venv/bin:$PATH

# The build stage installs the context into the venv
FROM developer AS build
# Requires buildkit 0.17.0
COPY --chmod=o+wrX . /workspaces/spectroscopy-bluesky
WORKDIR /workspaces/spectroscopy-bluesky
RUN touch dev-requirements.txt && pip install -c dev-requirements.txt .


# The runtime stage copies the built venv into a slim runtime container
FROM python:${PYTHON_VERSION}-slim AS runtime
# Add apt-get system dependecies for runtime here if needed
COPY --from=build /venv/ /venv/
ENV PATH=/venv/bin:$PATH

# change this entrypoint if it is not the same as the repo
ENTRYPOINT ["spectroscopy-bluesky"]
CMD ["--version"]
