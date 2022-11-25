# import os
#
# from troncos.logs import init_logging_basic
# init_logging_basic(
#     level=os.environ.get("LOG_LEVEL", "INFO"),
#     formatter=os.environ.get("LOG_FORMATTER", "cli")  # Use "logfmt" or "json" in k8s
# )
#
# from troncos.traces import init_tracing_basic
# init_tracing_basic(
#     service_name="whatever",
#     service_env="local",
#     service_version="testing",
#     endpoint="http://localhost:4317/v1/traces",
#     endpoint_dd="http://localhost:8083",
# )
#
# import asyncio
# import logging
# import time
# from troncos.traces.decorate import trace_module, trace_block
# from troncos.profiling.profiler import python_pprof
# python_pprof()
#
#
# import ddtrace
#
# async def mythang(msg):
#     await asyncio.sleep(1)
#     print(msg)
#
# async def main():
#     with trace_block("hello") as span:
#         span.set_tag("gummier", "bestur")
#         await asyncio.gather(mythang("einn"), mythang("tveir"))
#         try:
#             with trace_block("hello2", resource="someres", service="something"):
#                 logging.getLogger("ahaha").info("TÖFF")
#                 raise ValueError("OMG")
#         except:
#             pass
#
# trace_module()
#
# if __name__ == '__main__':
#     loop = asyncio.get_event_loop()
#     loop.run_until_complete(main())
#
#
# # Flush
# ddtrace.tracer.flush()
# # for s in troncos.newtrace.setup.otel_span_processors:
# #     s.force_flush(5000)
#
# time.sleep(4)
