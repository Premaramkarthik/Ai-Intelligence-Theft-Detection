Act as a senior Computer Vision Architect, Distributed Systems Engineer, and MLOps expert.

Your task is to FIX a real-time multi-camera OpenCV + AI pipeline by addressing a list of CRITICAL, HIGH, MEDIUM, SECURITY, and REFACTORING issues.

-----------------------------------
MANDATORY RULES (NON-NEGOTIABLE)
-----------------------------------

1. You MUST use web search
2. You MUST verify ALL fixes using:
   - OpenCV official documentation
   - Python asyncio official docs
   - Milvus official docs
   - Kafka official docs
   - GitHub reference implementations
3. NO hallucination
4. NO guessing APIs
5. NO patch fixes — redesign properly where needed
6. ALL fixes must be:
   - correct
   - production-grade
   - scalable

-----------------------------------
SYSTEM CONTEXT
-----------------------------------

Pipeline includes:

- OpenCV pipeline (videoio, imgproc, video, calib3d, bgsegm)
- YOLO detection (Ultralytics)
- Tracking (ByteTrack / Roboflow tracker)
- Body ReID (OSNet)
- Identity system (Milvus / FAISS)
- Async pipeline (asyncio)
- Kafka streaming
- Multi-camera sync

-----------------------------------
OBJECTIVE
-----------------------------------

Fix ALL identified issues while:

- maintaining correctness
- improving architecture
- ensuring scalability
- aligning with official best practices

-----------------------------------
STEP 0 — VERIFY BEFORE FIXING

For EACH issue:

- Search official documentation
- Validate correct behavior
- Confirm best practice from GitHub

Do NOT fix blindly.

-----------------------------------
fix the issues you have mentioned 
-----------------------------------
FINAL REQUIREMENT

- The result MUST be:
  - production-ready
  - scalable
  - correct
- No shortcuts
- No vague explanations