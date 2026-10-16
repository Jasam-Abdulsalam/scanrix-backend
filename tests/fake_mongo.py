"""A tiny in-memory stand-in for a Motor collection: enough operators for the history/favorites code
($or, $in, $lt, equality), compound sort, limit, upsert with $setOnInsert, deletes, counts."""
from bson import ObjectId


def _matches(doc, filt):
    for key, cond in filt.items():
        if key == "$or":
            if not any(_matches(doc, sub) for sub in cond):
                return False
        elif isinstance(cond, dict) and set(cond) <= {"$lt", "$in"}:
            value = doc.get(key)
            if "$lt" in cond and not (value is not None and value < cond["$lt"]):
                return False
            if "$in" in cond and value not in cond["$in"]:
                return False
        elif doc.get(key) != cond:
            return False
    return True


class Result:
    def __init__(self, n=0, upserted=None):
        self.deleted_count = n
        self.upserted_id = upserted


class Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, spec, direction=None):
        keys = [(spec, direction)] if direction is not None else list(spec)
        for field, d in reversed(keys):
            self.docs = sorted(self.docs, key=lambda x, f=field: x[f], reverse=d == -1)
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, length=None):
        return list(self.docs)


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs if docs is not None else []
        self.find_calls = 0

    def find(self, filt=None, projection=None):
        self.find_calls += 1
        return Cursor([d for d in self.docs if _matches(d, filt or {})])

    async def find_one(self, filt, projection=None):
        return next((d for d in self.docs if _matches(d, filt)), None)

    async def count_documents(self, filt):
        return sum(1 for d in self.docs if _matches(d, filt))

    async def update_one(self, filt, update, upsert=False):
        doc = await self.find_one(filt)
        if doc is not None:
            return Result()
        if not upsert:
            return Result()
        new = {"_id": ObjectId(), **{k: v for k, v in filt.items() if not k.startswith("$")}, **update.get("$setOnInsert", {})}
        self.docs.append(new)
        return Result(upserted=new["_id"])

    async def delete_one(self, filt):
        hit = [d for d in self.docs if _matches(d, filt)][:1]
        for d in hit:
            self.docs.remove(d)
        return Result(len(hit))

    async def delete_many(self, filt):
        hit = [d for d in self.docs if _matches(d, filt)]
        for d in hit:
            self.docs.remove(d)
        return Result(len(hit))
