"""M3 分批补全器：按表分批 + 并发限制，避免上下文超限与 QPS 过高"""

import asyncio

from agent.llm.schema import TableEnrich


class Enricher:
    def __init__(self, llm_client, batch_size: int = 10, concurrency: int = 3):
        self.llm_client = llm_client
        self.batch_size = batch_size
        self.concurrency = concurrency

    async def enrich_all(self, tables) -> list[tuple]:
        """对一批表做业务补全，返回 [(table, TableEnrich), ...]"""
        sem = asyncio.Semaphore(self.concurrency)
        results = []
        for i in range(0, len(tables), self.batch_size):
            batch = tables[i:i + self.batch_size]
            batch_results = await asyncio.gather(
                *(self._enrich_one(t, sem) for t in batch)
            )
            results.extend(batch_results)
        return results

    async def _enrich_one(self, table, sem: asyncio.Semaphore):
        async with sem:
            enrich: TableEnrich = await self.llm_client.enrich_table(table)
            return (table, enrich)
