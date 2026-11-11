execute_process(COMMAND "${PROGRAM}" --replay-first "${CONTENT}" "${SCENARIO}"
    OUTPUT_VARIABLE first ERROR_VARIABLE error RESULT_VARIABLE status)
if(NOT status STREQUAL "0")
    message(FATAL_ERROR "Replay failed: ${error}")
endif()
set(invalid "${CMAKE_CURRENT_BINARY_DIR}/unsorted-replay.json")
file(WRITE "${invalid}" "{\"seed\":1,\"ticks\":10,\"actions\":[{\"tick\":1,\"action\":\"start\"},{\"tick\":0,\"action\":\"start\"}]}")
execute_process(COMMAND "${PROGRAM}" --replay-first "${CONTENT}" "${invalid}"
    RESULT_VARIABLE invalid_status ERROR_VARIABLE invalid_error OUTPUT_QUIET)
if(NOT invalid_status STREQUAL "1" OR NOT invalid_error MATCHES "sorted by tick")
    message(FATAL_ERROR "Unsorted replay inputs were not rejected with an actionable error")
endif()
execute_process(COMMAND "${PROGRAM}" --replay-first "${CONTENT}" "${SCENARIO}"
    OUTPUT_VARIABLE second RESULT_VARIABLE status)
if(NOT status STREQUAL "0" OR NOT first STREQUAL second)
    message(FATAL_ERROR "Identical replay inputs produced different results")
endif()
if(NOT first MATCHES "\"event\":\"sun_dropped\"[^\n]*\"tick\":120[,}]" OR
   NOT first MATCHES "\"event\":\"wave_started\"[^\n]*\"tick\":720[,}]")
    message(FATAL_ERROR "Replay is missing the reference first sun or first wave timing")
endif()
