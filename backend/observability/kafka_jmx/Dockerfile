FROM confluentinc/cp-kafka:8.1.1

USER root

RUN mkdir -p /opt/jmx-exporter /etc/jmx-exporter \
    && curl --fail --show-error --silent --location \
      --output /opt/jmx-exporter/jmx_prometheus_javaagent-1.5.0.jar \
      https://github.com/prometheus/jmx_exporter/releases/download/1.5.0/jmx_prometheus_javaagent-1.5.0.jar
