FROM alpine:3.21
RUN apk add --no-cache ffmpeg
ENTRYPOINT ["ffmpeg"]
CMD ["-re", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=15", "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-f", "rtsp", "-rtsp_transport", "tcp", "rtsp://sample-gateway:8554/pattern"]
