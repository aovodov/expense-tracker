FROM jenkins/jenkins:2.580.3-lts-jdk21

ARG EXPENSE_TRACKER_REV=bfc30aa201e61170ff207e0211c07f010266b4a9
ARG TESTOPS_PLUGIN_VERSION=4.2.1

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl python3 python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && install -d /opt/jenkins-demo/project \
    && curl -fsSL "https://codeload.github.com/aovodov/expense-tracker/tar.gz/${EXPENSE_TRACKER_REV}" -o /tmp/project.tar.gz \
    && tar -xzf /tmp/project.tar.gz -C /opt/jenkins-demo/project --strip-components=1 \
    && rm /tmp/project.tar.gz \
    && python3 -m venv /opt/jenkins-demo/venv \
    && /opt/jenkins-demo/venv/bin/pip install --no-cache-dir pytest==9.2.0 allure-pytest==2.16.2 \
    && curl -fsSL "https://dl.qatools.ru/repository/public/qatools-jenkins-plugin/qatools-jenkins-plugin-${TESTOPS_PLUGIN_VERSION}.hpi" \
        -o /opt/jenkins-demo/testops-jenkins.hpi

USER jenkins
COPY plugins.txt /tmp/demo-plugins.txt
RUN jenkins-plugin-cli --plugin-file /tmp/demo-plugins.txt \
    && cp /opt/jenkins-demo/testops-jenkins.hpi /usr/share/jenkins/ref/plugins/
COPY jenkins.yaml bootstrap.py /opt/jenkins-demo/
ENV CASC_JENKINS_CONFIG=/opt/jenkins-demo/jenkins.yaml \
    JAVA_OPTS=-Djenkins.install.RunSetupWizard=false
ENTRYPOINT ["/usr/bin/tini", "-g", "--", "python3", "/opt/jenkins-demo/bootstrap.py"]
