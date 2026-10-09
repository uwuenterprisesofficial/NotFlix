# The series service as a container (docker build -t notflix-series desktop/stack/series-api).
# The desktop app doesn't use this: it runs the service itself, as an executable on the PC
# (desktop/scripts/prepare-stack.mjs).
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY SeriesApi.csproj .
RUN dotnet restore
COPY . .
RUN dotnet publish -c Release -o /out --no-restore \
    -p:SelfContained=false -p:PublishSingleFile=false

FROM mcr.microsoft.com/dotnet/aspnet:8.0
WORKDIR /app
COPY --from=build /out .
ENV SERIES_HOST=https://serienstream.to/
EXPOSE 8000
ENTRYPOINT ["./series-api", "--urls", "http://0.0.0.0:8000"]
