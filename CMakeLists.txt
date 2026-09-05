# ---------------------------------------------------------------------------
#  Nearby - a location-based dating web app (MVP)
#
#  ONE COMMAND TO RUN IT:
#
#      cmake -P CMakeLists.txt
#
#  That finds Python, creates + seeds the SQLite database on first run, and
#  starts the web server on http://127.0.0.1:8000
#
#  Options (script mode):
#      cmake -DPORT=9000 -P CMakeLists.txt      # different port
#      cmake -DHOST=0.0.0.0 -P CMakeLists.txt   # expose on the LAN
#      cmake -DACTION=seed  -P CMakeLists.txt   # (re)build + seed the DB only
#      cmake -DACTION=reset -P CMakeLists.txt   # wipe the DB, reseed, then run
#      cmake -DACTION=check -P CMakeLists.txt   # self-test, no server
#
#  Classic out-of-source flow works too:
#      cmake -S . -B build && cmake --build build --target run
#      cmake --build build --target seed | reset | check
#
#  There are no third-party dependencies: the app runs on the Python standard
#  library alone, so there is no venv to create and nothing to download.
# ---------------------------------------------------------------------------

cmake_minimum_required(VERSION 3.16)

set(NEARBY_ROOT "${CMAKE_CURRENT_LIST_DIR}")
set(NEARBY_MIN_PY_MAJOR 3)
set(NEARBY_MIN_PY_MINOR 8)

# --- locate a usable interpreter -------------------------------------------
function(nearby_find_python OUT_VAR)
  set(_candidates
      python3.13 python3.12 python3.11 python3.10 python3.9 python3 python)
  set(_found "")
  foreach(_name IN LISTS _candidates)
    find_program(_py_${_name} NAMES ${_name})
    if(_py_${_name})
      execute_process(
        COMMAND "${_py_${_name}}" -c
                "import sys; print('%d %d' % sys.version_info[:2])"
        OUTPUT_VARIABLE _ver
        OUTPUT_STRIP_TRAILING_WHITESPACE
        ERROR_QUIET
        RESULT_VARIABLE _rc)
      if(_rc EQUAL 0)
        string(REPLACE " " ";" _ver_list "${_ver}")
        list(GET _ver_list 0 _major)
        list(GET _ver_list 1 _minor)
        if(_major GREATER_EQUAL ${NEARBY_MIN_PY_MAJOR}
           AND NOT (_major EQUAL ${NEARBY_MIN_PY_MAJOR}
                    AND _minor LESS ${NEARBY_MIN_PY_MINOR}))
          set(_found "${_py_${_name}}")
          message(STATUS "Nearby: using Python ${_major}.${_minor} at ${_found}")
          break()
        endif()
      endif()
    endif()
  endforeach()

  if(NOT _found)
    message(FATAL_ERROR
      "Nearby needs Python ${NEARBY_MIN_PY_MAJOR}.${NEARBY_MIN_PY_MINOR} or newer on PATH.")
  endif()
  set(${OUT_VAR} "${_found}" PARENT_SCOPE)
endfunction()

# --- run one of the app's subcommands --------------------------------------
function(nearby_invoke)
  nearby_find_python(PY)

  if(NOT DEFINED ACTION OR ACTION STREQUAL "")
    set(ACTION "run")
  endif()
  if(NOT DEFINED HOST OR HOST STREQUAL "")
    set(HOST "127.0.0.1")
  endif()
  if(NOT DEFINED PORT OR PORT STREQUAL "")
    set(PORT "8000")
  endif()

  # -u keeps the startup banner from sitting in Python's buffer behind CMake.
  set(_args "-u" "${NEARBY_ROOT}/run.py" "${ACTION}"
            "--host" "${HOST}" "--port" "${PORT}")

  execute_process(
    COMMAND "${PY}" ${_args}
    WORKING_DIRECTORY "${NEARBY_ROOT}"
    RESULT_VARIABLE _rc)

  if(NOT _rc EQUAL 0)
    # Ctrl-C on the dev server is a normal way to stop; don't call it a failure.
    if(_rc EQUAL 130 OR _rc STREQUAL "Interrupt")
      message(STATUS "Nearby: server stopped.")
    else()
      message(FATAL_ERROR "Nearby: '${ACTION}' exited with ${_rc}")
    endif()
  endif()
endfunction()

# ---------------------------------------------------------------------------
#  `cmake -P CMakeLists.txt` lands here: do the work immediately.
# ---------------------------------------------------------------------------
if(CMAKE_SCRIPT_MODE_FILE)
  nearby_invoke()
  return()
endif()

# ---------------------------------------------------------------------------
#  Configured-project mode: expose the same actions as build targets, each of
#  which simply re-enters this file in script mode.
# ---------------------------------------------------------------------------
project(nearby VERSION 0.1.0 LANGUAGES NONE)

nearby_find_python(NEARBY_PYTHON)

set(NEARBY_HOST "127.0.0.1" CACHE STRING "Interface the dev server binds to")
set(NEARBY_PORT "8000"      CACHE STRING "Port the dev server listens on")

foreach(_action run seed reset check)
  add_custom_target(${_action}
    COMMAND ${CMAKE_COMMAND}
            -DACTION=${_action}
            -DHOST=${NEARBY_HOST}
            -DPORT=${NEARBY_PORT}
            -P "${CMAKE_CURRENT_LIST_FILE}"
    WORKING_DIRECTORY "${NEARBY_ROOT}"
    USES_TERMINAL
    VERBATIM
    COMMENT "nearby: ${_action}")
endforeach()

add_custom_target(nearby ALL
  COMMAND ${CMAKE_COMMAND} -E echo
          "Nearby is ready. Start it with:  cmake --build . --target run"
  VERBATIM)
