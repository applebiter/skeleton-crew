# Architecture: Opportunistic Task Decomposition

## Core Philosophy

**Work with what's available. Break complex tasks into small, simple ones.**

This system does NOT assume:
- A "heavy compute" node exists
- Any specific node is always available
- Tasks must be assigned to particular hardware
- Large models are better than small ones

Instead, it assumes:
- Any node might go offline
- Smaller tasks are more reliable
- Multiple small LLM calls beat one large one
- Local computation is preferable
- The cluster adapts to available resources

## Design Principles

### 1. Every Node is Capable

All nodes can:
- Run 3B models (granite4:3b, ministral-3:3b)
- Process STT with Vosk or Whisper base/small
- Synthesize speech with Piper
- Execute agent tasks
- Handle JACK audio

**No specialization required.** Differences in hardware (GTX 1050ti vs RTX 3060) are *optimization opportunities*, not *requirements*.

### 2. Task Decomposition Over Power

Instead of:
```
"Transcribe this 2-hour film" → Send to Windows node with Whisper large
```

Do this:
```
"Transcribe this 2-hour film"
  → Chunk into 10-minute segments
  → Distribute across available nodes
  → Each node uses Whisper base (fast enough)
  → Merge results in database
```

**Benefits:**
- Works if Windows node is offline
- Faster (parallel processing)
- More reliable (failures affect only one chunk)
- Utilizes all hardware

### 3. Iterative LLM Usage

Instead of:
```python
# One big prompt with full context
result = llm.chat(
    messages=entire_conversation_history,
    max_tokens=4096
)
```

Do this:
```python
# Many small, focused calls
for step in range(max_iterations):
    next_action = llm.chat(
        messages=recent_context[-5:],  # Last 5 messages only
        max_tokens=512,                # Small response
        prompt="What's the NEXT single action?"
    )
    execute_action(next_action)
    recent_context.append(next_action)
```

**Benefits:**
- Faster response time
- Lower memory usage
- 3B models handle it fine
- Can run on any node
- More debuggable

### 4. Opportunistic Scheduling

The **Capability Router** doesn't assign work to specific nodes. Instead:

1. Query database for nodes with required capability
2. Filter by availability and load
3. Pick least-loaded node
4. If it fails, try another
5. No hard dependencies on any specific node

```python
# Not this:
if task_type == "heavy_llm":
    route_to("windows-main")  # Hard dependency!

# This:
nodes = find_nodes_with_capability("llm")
available = [n for n in nodes if n.load < 0.7]
node = min(available, key=lambda n: n.load)
```

### 5. Graceful Degradation

If the ideal resource isn't available, use what is:

```python
# Try in order of preference (example with vision task)
for model in ["ministral-3:7b", "ministral-3:3b"]:
    if model_available(model):
        return use_model(model)

# For agent/tool tasks
for model in ["granite4:8b", "granite4:3b"]:
    if model_available(model):
        return use_model(model)

# Still works even if only smallest model available
```

## Task Decomposition Patterns

### Media Transcription

**Large file → Small chunks:**

```python
# Don't route entire file to "best" node
# Instead:

1. Split audio into N-minute chunks
2. Create transcription job for each chunk in database
3. Any node with STT capability can claim a job
4. Process in parallel across cluster
5. Store results with timestamps in database
6. Merge when all complete

# If nodes go offline, remaining nodes pick up unclaimed jobs
```

### Conversational Agent

**Complex query → Iterative steps:**

```python
User: "Analyze my audio files, find duplicates, and clean up"

# Not: One massive prompt to powerful model
# Instead: Many small steps on any node

Step 1: List files → llm.chat("What files should I check?")
Step 2: For each file → Get metadata
Step 3: Compare → llm.chat("These two look similar, are they duplicates?")
Step 4: Confirm → Ask user
Step 5: Execute → Delete files
Step 6: Summarize → llm.chat("Generate brief summary")

# Each step is ~100 tokens, 3B model handles it fine
# Total work distributes across available nodes
```

### RAG Queries

**Large corpus → Progressive search:**

```python
# Not: Retrieve 100 chunks, send all to LLM at once
# Instead: Iterative refinement

Step 1: Embed query (any node with embedding model)
Step 2: Retrieve top 5 chunks (database query)
Step 3: Ask LLM: "Is this relevant?" (3B model)
Step 4: If yes, synthesize answer
Step 5: If no, retrieve next 5 and repeat

# More token-efficient
# Works on small models
# No single node bottleneck
```

## Hardware Utilization Strategy

### Your 6 Linux Nodes (GTX 1050ti, 32GB RAM)

**Each can run:**
- Ollama with 3B models (Granite4, Ministral-3 for vision/OCR)
- Tool/function calling with Granite4 (for agent tasks)
- Vosk for real-time STT
- Whisper base/small for accuracy STT
- Piper for TTS
- JACK audio processing

**Parallel processing example:**
```
Transcribe 1-hour podcast:
- Split into 6x 10-minute segments
- Each node processes one segment (Whisper small)
- Time: ~5 minutes per segment
- Total time: ~5 minutes (vs 30 minutes single-node)

Agent task with tools:
- Each node runs Granite4:3b with function calling
- Break complex task into tool calls
- Distribute tool execution across nodes
- Merge results

OCR batch processing:
- Use Ministral-3:3b for image/document OCR
- Each node processes subset of images
- Extract text in parallel
- Combine results
```

### Windows Node (Optional Enhancement)

**When available:**
- Can run larger models (8B+)
- Can run Whisper medium/large
- Can process more chunks simultaneously
- Same tool-calling capabilities with bigger models

**When offline:**
- System continues normally
- Tasks take slightly longer
- Quality still good (Whisper base/small accurate, Granite4 very capable)
- Tool calling still works on all Linux nodes
- Vision/OCR continues with Ministral-3

## Implementation Examples

### Agent Framework

```python
class TinyStepAgent:
    """Agent that breaks tasks into minimal steps."""
    
    async def execute_task(self, user_request: str):
        context = [{"role": "user", "content": user_request}]
        
        for i in range(self.max_iterations):
            # Small LLM call for next action
            response = await self.llm.chat(LLMRequest(
                messages=context[-5:],  # Only recent context
                max_tokens=256,         # Small response
                temperature=0.3
            ))
            
            # Parse action
            action = self.parse_action(response.content)
            
            if action.type == "done":
                return action.result
            
            # Execute single action
            result = await self.execute_action(action)
            
            # Update context
            context.append({
                "role": "assistant",
                "content": f"Action: {action.type}"
            })
            context.append({
                "role": "user",
                "content": f"Result: {result}"
            })
```

### Distributed Transcription

```python
class ChunkedTranscription:
    """Break large files into chunks, process in parallel."""
    
    async def transcribe_file(self, file_path: str):
        # 1. Chunk audio
        chunks = await self.chunk_audio(file_path, chunk_minutes=10)
        
        # 2. Create jobs in database
        job_ids = []
        for i, chunk_data in enumerate(chunks):
            job_id = await self.db.execute("""
                INSERT INTO transcription_jobs 
                (file_path, chunk_index, audio_data, status)
                VALUES ($1, $2, $3, 'pending')
                RETURNING id
            """, file_path, i, chunk_data)
            job_ids.append(job_id)
        
        # 3. Wait for completion (any node can claim jobs)
        while True:
            completed = await self.db.fetchval("""
                SELECT COUNT(*) FROM transcription_jobs
                WHERE id = ANY($1) AND status = 'completed'
            """, job_ids)
            
            if completed == len(job_ids):
                break
            
            await asyncio.sleep(1)
        
        # 4. Merge results
        transcripts = await self.db.fetch("""
            SELECT chunk_index, result->>'text' as text
            FROM transcription_jobs
            WHERE id = ANY($1)
            ORDER BY chunk_index
        """, job_ids)
        
        return " ".join(t['text'] for t in transcripts)
```

### Worker Pattern

```python
class TranscriptionWorker:
    """Worker that claims and processes jobs from queue."""
    
    async def run(self):
        while True:
            # Claim a job
            job = await self.db.fetchrow("""
                UPDATE transcription_jobs
                SET status = 'processing',
                    assigned_node = $1,
                    started_at = NOW()
                WHERE id = (
                    SELECT id FROM transcription_jobs
                    WHERE status = 'pending'
                    ORDER BY priority DESC, created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING *
            """, self.node_id)
            
            if not job:
                await asyncio.sleep(5)
                continue
            
            try:
                # Process with whatever STT we have available
                result = await self.stt.transcribe(job['audio_data'])
                
                # Store result
                await self.db.execute("""
                    UPDATE transcription_jobs
                    SET status = 'completed',
                        result = $1,
                        completed_at = NOW()
                    WHERE id = $2
                """, {'text': result.text}, job['id'])
                
            except Exception as e:
                # Mark failed, another worker can retry
                await self.db.execute("""
                    UPDATE transcription_jobs
                    SET status = 'pending',
                        error = $1,
                        assigned_node = NULL
                    WHERE id = $2
                """, str(e), job['id'])
```

## Configuration Philosophy

### Don't Do This:

```yaml
roles:
  - "llm_light"  # Only 3B models
  
routing:
  overrides:
    llm_heavy:
      prefer_node: "windows-main"  # Hard dependency!
```

### Do This:

```yaml
roles:
  - "llm"        # Any models that fit
  - "stt_batch"  # Any Whisper model
  - "agent"      # Can execute tasks

routing:
  load_balance: true
  decomposition:
    max_task_size: "small"
    prefer_parallel: true
```

## Benefits of This Approach

1. **Resilience**: No single point of failure
2. **Scalability**: Add nodes, get more throughput
3. **Simplicity**: All nodes are similar
4. **Maintainability**: No special cases
5. **Cost**: Use what you have, not what you buy
6. **Speed**: Parallel processing often faster than one big node
7. **Debuggability**: Small tasks easier to trace

## When to Use Specialized Nodes

The system CAN use specialized hardware when available, but doesn't REQUIRE it:

```python
# If Windows node is available and has Whisper large
if node.has_model("whisper:large"):
    # Use it for critical accuracy tasks
    use_node(node)
else:
    # Fall back to chunked processing with Whisper small
    # across multiple nodes - still works, slightly less accurate
    use_distributed_fallback()
```

This is the difference between **optimization** and **dependency**.

## Summary

**Old mindset:** "I need a powerful machine to do AI tasks"  
**New mindset:** "I have 6 machines, let's break the work into 6 pieces"

**Old approach:** Route complex tasks to the most powerful node  
**New approach:** Break complex tasks into simple ones any node can handle

**Old problem:** Windows node offline = system degraded  
**New solution:** Windows node offline = slightly slower but fully functional

This is true **distributed computing** - not just "multiple machines", but "work adapts to available resources."
