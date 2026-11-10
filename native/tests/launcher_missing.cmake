execute_process(
    COMMAND "${PROGRAM}" --launcher-smoke "${ASSET_ROOT}"
    RESULT_VARIABLE result
    ERROR_VARIABLE diagnostic)

if(NOT result STREQUAL "1" OR NOT diagnostic MATCHES "launcher\\.png")
    message(FATAL_ERROR "Expected exit 1 and a launcher.png diagnostic. Got ${result}: ${diagnostic}")
endif()
