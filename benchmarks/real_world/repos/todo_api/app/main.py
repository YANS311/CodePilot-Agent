"""FastAPI entry point for Todo API."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.storage import TodoStorage
from app.service import TodoService

app = FastAPI(title="Todo API")
storage = TodoStorage()
service = TodoService(storage)


class CreateTodoRequest(BaseModel):
    title: str


@app.post("/todos")
def create_todo(req: CreateTodoRequest):
    todo = service.create(req.title)
    return {"id": todo.id, "title": todo.title, "done": todo.done}


@app.get("/todos")
def list_todos():
    return [{"id": t.id, "title": t.title, "done": t.done} for t in service._storage.list_all()]


@app.get("/todos/pending")
def list_pending():
    return [{"id": t.id, "title": t.title} for t in service.list_pending()]


@app.post("/todos/{todo_id}/complete")
def complete_todo(todo_id: int):
    todo = service.complete(todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    return {"id": todo.id, "done": todo.done}


@app.delete("/todos/{todo_id}")
def delete_todo(todo_id: int):
    result = service.delete(todo_id)
    if not result:
        raise HTTPException(status_code=404, detail="Todo not found")
    return {"deleted": True}
