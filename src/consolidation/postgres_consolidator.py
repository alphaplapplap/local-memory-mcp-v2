import asyncpg
import json
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
import logging

class PostgreSQLConsolidator:
    def __init__(self, connection_string: str, embedding_client):
        self.connection_string = connection_string
        self.embedding_client = embedding_client
        self.logger = logging.getLogger(__name__)

    async def consolidate_memories(self, domain_id: Optional[str] = None,
                                 days_back: int = 30) -> Dict:
        """
        Consolidate memories using dream-inspired algorithms
        Adapted from doobidoo's consolidation system
        """
        domain = domain_id or 'default'
        table_name = f"{domain}_memories"

        try:
            conn = await asyncpg.connect(self.connection_string)
        except Exception as e:
            self.logger.error(f"Failed to connect to database: {e}")
            return {"error": f"Database connection failed: {e}"}

        try:
            # Phase 1: Identify consolidation candidates
            candidates = await self._find_consolidation_candidates(conn, table_name, days_back)
            
            if not candidates:
                return {
                    "status": "no_candidates",
                    "message": f"No memories found for consolidation in domain '{domain}'",
                    "processed": 0,
                    "clusters_created": 0,
                    "memories_archived": 0,
                    "consolidated_memories": 0
                }

            # Phase 2: Cluster similar memories
            clusters = await self._cluster_similar_memories(candidates)
            
            if not clusters:
                return {
                    "status": "no_clusters",
                    "message": "No similar memories found to cluster",
                    "processed": len(candidates),
                    "clusters_created": 0,
                    "memories_archived": 0,
                    "consolidated_memories": 0
                }

            # Phase 3: Generate consolidated memories
            consolidated = await self._generate_consolidated_memories(clusters)

            # Phase 4: Archive or merge original memories
            archived_count = await self._archive_consolidated_memories(conn, consolidated, table_name)

            return {
                "status": "success",
                "processed": len(candidates),
                "clusters_created": len(clusters),
                "memories_archived": archived_count,
                "consolidated_memories": len(consolidated)
            }
        except Exception as e:
            self.logger.error(f"Consolidation failed: {e}")
            return {"error": f"Consolidation failed: {e}"}
        finally:
            await conn.close()

    async def _find_consolidation_candidates(self, conn, table_name, days_back) -> List[Dict]:
        """Find memories eligible for consolidation"""
        cutoff_date = datetime.now() - timedelta(days=days_back)

        try:
            # Check if table exists first
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = $1
                )
            """, table_name)
            
            if not table_exists:
                self.logger.warning(f"Table {table_name} does not exist")
                return []

            # Use dynamic table name
            sql = f"""
                SELECT id, content, metadata, embedding, created_at
                FROM {table_name}
                WHERE created_at >= $1
                AND NOT COALESCE((metadata->>'consolidated')::boolean, false)
                ORDER BY created_at DESC
            """

            rows = await conn.fetch(sql, cutoff_date)

            candidates = []
            for row in rows:
                # Parse metadata if it's a string
                metadata = row["metadata"]
                if isinstance(metadata, str):
                    try:
                        import json
                        metadata = json.loads(metadata)
                    except:
                        metadata = {}
                elif metadata is None:
                    metadata = {}
                
                candidates.append({
                    "id": row["id"],
                    "content": row["content"],
                    "metadata": metadata,
                    "embedding": row["embedding"],
                    "created_at": row["created_at"]
                })
            
            return candidates
        except Exception as e:
            self.logger.error(f"Error finding consolidation candidates: {e}")
            return []

    async def _cluster_similar_memories(self, memories: List[Dict]) -> List[List[Dict]]:
        """
        Cluster similar memories using cosine similarity
        Adapted from doobidoo's clustering algorithm
        """
        clusters = []
        used_indices = set()

        similarity_threshold = 0.5  # Lowered to match clustering system

        for i, memory in enumerate(memories):
            if i in used_indices:
                continue

            cluster = [memory]
            used_indices.add(i)

            # Find similar memories
            for j, other_memory in enumerate(memories[i+1:], i+1):
                if j in used_indices:
                    continue

                # Calculate cosine similarity between embeddings
                similarity = self._cosine_similarity(
                    memory["embedding"],
                    other_memory["embedding"]
                )

                if similarity > similarity_threshold:
                    cluster.append(other_memory)
                    used_indices.add(j)

            # Only create clusters with multiple memories
            if len(cluster) > 1:
                clusters.append(cluster)

        return clusters

    def _cosine_similarity(self, vec1, vec2) -> float:
        """Calculate cosine similarity between two vectors"""
        import math
        
        # Handle None or invalid embeddings
        if vec1 is None or vec2 is None:
            return 0.0
            
        # Convert to list if needed
        if isinstance(vec1, str):
            try:
                vec1 = eval(vec1)  # Safe for numeric lists
            except:
                return 0.0
        elif not isinstance(vec1, list):
            try:
                vec1 = list(vec1)
            except:
                return 0.0
                
        if isinstance(vec2, str):
            try:
                vec2 = eval(vec2)  # Safe for numeric lists
            except:
                return 0.0
        elif not isinstance(vec2, list):
            try:
                vec2 = list(vec2)
            except:
                return 0.0
        
        # Ensure vectors have the same length
        if len(vec1) != len(vec2):
            return 0.0
            
        # Ensure all elements are numeric
        try:
            vec1 = [float(x) for x in vec1]
            vec2 = [float(x) for x in vec2]
        except (ValueError, TypeError):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(a * a for a in vec2))

        if magnitude1 == 0 or magnitude2 == 0:
            return 0

        return dot_product / (magnitude1 * magnitude2)

    async def _generate_consolidated_memories(self, clusters: List[List[Dict]]) -> List[Dict]:
        """
        Generate consolidated memories from clusters
        This is where you'd implement LLM-based consolidation
        """
        consolidated = []

        for cluster in clusters:
            # Extract common themes and key information
            contents = [memory["content"] for memory in cluster]

            # This is where you could use Ollama to generate a consolidated summary
            # For now, we'll create a simple consolidation
            consolidated_content = self._simple_consolidation(contents)

            # Merge metadata
            merged_metadata = self._merge_metadata([m["metadata"] for m in cluster])
            merged_metadata["consolidated"] = True
            merged_metadata["source_count"] = len(cluster)
            merged_metadata["consolidated_at"] = datetime.now().isoformat()

            consolidated.append({
                "content": consolidated_content,
                "metadata": merged_metadata,
                "source_memory_ids": [m["id"] for m in cluster]
            })

        return consolidated

    def _simple_consolidation(self, contents: List[str]) -> str:
        """
        Simple consolidation strategy (you could enhance with LLM)
        """
        if len(contents) == 1:
            return contents[0]

        # For now, create a summary format
        summary = f"Consolidated insight from {len(contents)} related memories:\n\n"

        for i, content in enumerate(contents, 1):
            summary += f"{i}. {content}\n"

        return summary

    def _merge_metadata(self, metadatas: List[Dict]) -> Dict:
        """Merge metadata from multiple memories"""
        merged = {}
        all_tags = set()

        for metadata in metadatas:
            if metadata is None:
                continue
                
            # Collect all tags
            if "tags" in metadata and metadata["tags"]:
                if isinstance(metadata["tags"], list):
                    all_tags.update(metadata["tags"])
                elif isinstance(metadata["tags"], str):
                    all_tags.add(metadata["tags"])

            # Take the highest importance score
            if "importance" in metadata and metadata["importance"] is not None:
                try:
                    importance = float(metadata["importance"])
                    merged["importance"] = max(
                        merged.get("importance", 0),
                        importance
                    )
                except (ValueError, TypeError):
                    pass

        merged["tags"] = list(all_tags) if all_tags else []
        merged["memory_type"] = "consolidated"

        return merged

    async def _archive_consolidated_memories(self, conn, consolidated: List[Dict], table_name: str) -> int:
        """Archive original memories after consolidation"""
        archived_count = 0

        for consolidated_memory in consolidated:
            try:
                # Mark source memories as archived
                if consolidated_memory.get("source_memory_ids"):
                    await conn.execute(f"""
                        UPDATE {table_name}
                        SET metadata = metadata || '{{"archived": true, "archived_at": "{datetime.now().isoformat()}"}}'::jsonb
                        WHERE id = ANY($1)
                    """, consolidated_memory["source_memory_ids"])

                # Insert consolidated memory
                if self.embedding_client:
                    try:
                        embedding = await self.embedding_client.get_embedding(consolidated_memory["content"])
                    except Exception as e:
                        self.logger.warning(f"Failed to get embedding: {e}")
                        embedding = None
                else:
                    embedding = None

                # Generate a new ID for domain-specific tables (they use VARCHAR ids)
                import uuid
                new_id = str(uuid.uuid4())

                # Convert embedding to string format for pgvector
                if embedding is not None:
                    if isinstance(embedding, list):
                        embedding_str = '[' + ','.join(str(x) for x in embedding) + ']'
                    else:
                        embedding_str = str(embedding)
                else:
                    # Create a zero vector if no embedding available
                    embedding_str = '[0.0]'

                await conn.execute(f"""
                    INSERT INTO {table_name} (id, content, embedding, metadata, created_at)
                    VALUES ($1, $2, $3::vector, $4, NOW())
                """,
                    new_id,
                    consolidated_memory["content"],
                    embedding_str,
                    json.dumps(consolidated_memory["metadata"])
                )

                archived_count += len(consolidated_memory.get("source_memory_ids", []))
                
            except Exception as e:
                self.logger.error(f"Error archiving consolidated memory: {e}")
                continue

        return archived_count