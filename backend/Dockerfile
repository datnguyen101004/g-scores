FROM eclipse-temurin:21-jdk-alpine AS build
WORKDIR /build
COPY backend/.mvn/ .mvn/
COPY --chmod=755 backend/mvnw mvnw
COPY backend/pom.xml pom.xml
COPY backend/src/main/ src/main/
RUN --mount=type=cache,target=/root/.m2 ./mvnw -B -Dmaven.test.skip=true package

FROM eclipse-temurin:21-jre-alpine
WORKDIR /app
RUN addgroup -S -g 10001 spring && adduser -S -u 10001 -G spring spring
COPY --from=build --chown=spring:spring /build/target/backend-0.0.1-SNAPSHOT.jar app.jar
COPY --chown=spring:spring dataset/diem_thi_thpt_2024.csv dataset/diem_thi_thpt_2024.csv
ENV SERVER_PORT=8080 \
    SEED_CSV_PATH=/app/dataset/diem_thi_thpt_2024.csv
USER spring:spring
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]