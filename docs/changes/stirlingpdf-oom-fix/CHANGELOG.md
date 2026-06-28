# StirlingPDF OOM Crash Loop Fix

> **Date:** 2026-06-28
> **Severity:** HIGH
> **Status:** FIXED

## Problem

StirlingPDF container was in a crash loop, restarting every 3 seconds with `OutOfMemoryError: Metaspace`.

**Root Cause:**
1. Container had 1GB memory limit
2. StirlingPDF's auto-tuner set `MaxMetaspaceSize=128m` based on container memory
3. Spring Boot + PDF tools (LibreOffice, Tesseract, etc.) filled up 128m metaspace
4. JVM crashed with `OutOfMemoryError: Metaspace`
5. `-XX:+ExitOnOutOfMemoryError` caused JVM to exit
6. `-XX:+HeapDumpOnOutOfMemoryError` tried to create heap dump, but file already existed (same PID 256 each time)
7. Container restarted, same thing happened again

**Symptoms:**
- Container restarting every 3 seconds
- 10 stale heap dump files (2.5GB total) from repeated crashes
- `Unable to create /configs/heap_dumps/java_pid256.hprof: File exists`

## Solution

1. **Increased memory limit** from 1GB to 2GB in `docker-compose.yml`
   - Auto-tuner now sets `MaxMetaspaceSize=192m` (was 128m)
   - Max heap: 65% of 2GB = 1.3GB (was 614MB)
2. **Cleaned up stale heap dumps** (10 files, 2.5GB from repeated crashes)

## Files Changed

- `docker-compose.yml` — `mem_limit: 1g` → `mem_limit: 2g`

## Verification

- Container stable, API responding (HTTP 200)
- PID 288 (not the cursed 256)
- `MaxMetaspaceSize=192m` in startup logs
- Container running for >1 minute without crash

## Related

- BUG-17 in `docs/BUG-TRACKER.md`
