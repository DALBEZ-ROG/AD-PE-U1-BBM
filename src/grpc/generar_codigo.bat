@echo off
rem Genera mensajeria_pb2.py y mensajeria_pb2_grpc.py a partir de proto\mensajeria.proto
rem Se ejecuta desde la raiz del repositorio: src\grpc\generar_codigo.bat
python -m grpc_tools.protoc -I proto --python_out=src\grpc --grpc_python_out=src\grpc proto\mensajeria.proto
