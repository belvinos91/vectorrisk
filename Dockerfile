# VectorRisk backend + dashboard, one container.
# Uses conda-forge so rasterio/geopandas (GDAL) install cleanly.
FROM condaforge/miniforge3:latest

WORKDIR /app
RUN mamba install -y -c conda-forge \
        python=3.11 rasterio geopandas shapely pyproj numpy scipy xarray rioxarray netcdf4 \
        matplotlib pandas requests tqdm fastapi "uvicorn-standard" \
    && mamba clean -a -y

COPY . /app
RUN pip install --no-deps -e .

EXPOSE 8000
# Serves the API and the dashboard at http://<host>:8000/
CMD ["uvicorn", "vectorrisk.api:app", "--host", "0.0.0.0", "--port", "8000"]

