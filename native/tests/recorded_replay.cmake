foreach(result won lost)
    file(READ "${REPLAYS}/${result}.jsonl" expected)
    execute_process(COMMAND "${PROGRAM}" --replay-first "${CONTENT}" "${REPLAYS}/${result}.json"
        OUTPUT_VARIABLE actual ERROR_VARIABLE error RESULT_VARIABLE status)
    if(NOT status STREQUAL "0" OR NOT actual STREQUAL expected)
        message(FATAL_ERROR "The recorded ${result} battle did not replay identically: ${error}")
    endif()
endforeach()
