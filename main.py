# backend/main.py
from fastapi import FastAPI, HTTPException, UploadFile, File, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import uvicorn
import os
import json
import io
import csv
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Text, DateTime
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./fittracker.db")

engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

# ---------- модели БД ----------
class ExerciseDB(Base):
    __tablename__ = "exercises"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    tip = Column(Text, nullable=True)
    yt_search = Column(Text, nullable=True)
    sets = Column(Integer, default=1)
    reps = Column(Integer, default=1)
    weight = Column(Integer, default=0)

class WorkoutProgramDB(Base):
    __tablename__ = "programs"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    exercises = Column(Text, nullable=False)

class FinishedWorkoutDB(Base):
    __tablename__ = "finished_workouts"
    id = Column(Integer, primary_key=True, index=True)
    finished_at = Column(DateTime, default=datetime.utcnow)
    duration_sec = Column(Integer, nullable=False)
    exercises_done = Column(Text, nullable=False)

# ---------- Pydantic ----------
class Exercise(BaseModel):
    id: int
    name: str
    tip: str | None = None
    yt_search: str | None = None
    sets: int = 1
    reps: int = 1
    weight: int = 0

class WorkoutProgram(BaseModel):
    id: int | None = None
    title: str
    exercises: list[Exercise]

class FinishedWorkout(BaseModel):
    id: int
    finished_at: datetime
    duration_sec: int
    exercises_done: list[str]

# ---------- FastAPI ----------
app = FastAPI(title="FitTracker API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Dependency ----------
async def get_db():
    async with async_session() as session:
        yield session

# ---------- инициализация БД ----------
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as session:
        res = await session.execute(select(ExerciseDB).limit(1))
        if res.scalar_one_or_none() is None:
            start = [
                ExerciseDB(id=1, name="Жим лёжа", tip="Сведи лопатки, ступни на полу", yt_search="жим лёжа shorts техника", sets=4, reps=8, weight=60),
                ExerciseDB(id=2, name="Приседания", tip="Колени не выходят за носки", yt_search="приседания shorts техника", sets=4, reps=12, weight=0)
            ]
            session.add_all(start)
            await session.commit()

from sqlalchemy import select
@app.on_event("startup")
async def on_startup():
    await init_db()

# ---------- корневые энд-поинты ----------
@app.get("/")
def read_root():
    return {"message": "Сервер работает!"}

@app.get("/exercises", response_model=list[Exercise])
async def list_exercises(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(ExerciseDB))
    return [Exercise(**row.__dict__) for row in res.scalars()]

@app.get("/exercises/{exercise_id}", response_model=Exercise)
async def get_exercise(exercise_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(ExerciseDB).filter(ExerciseDB.id == exercise_id))
    row = res.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Упражнение не найдено")
    return Exercise(**row.__dict__)

# ---------- тренировки ----------
@app.post("/workouts/finish")
async def finish_workout(duration: int, exercises: list[str], db: AsyncSession = Depends(get_db)):
    finished = FinishedWorkoutDB(duration_sec=duration, exercises_done=json.dumps(exercises, ensure_ascii=False))
    db.add(finished)
    await db.commit()
    await db.refresh(finished)
    return {"ok": True, "workout_id": finished.id}

@app.get("/workouts/history", response_model=list[FinishedWorkout])
async def get_history(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(FinishedWorkoutDB).order_by(FinishedWorkoutDB.finished_at.desc()))
    return [
        FinishedWorkout(
            id=w.id,
            finished_at=w.finished_at,
            duration_sec=w.duration_sec,
            exercises_done=json.loads(w.exercises_done)
        )
        for w in res.scalars()
    ]

# ---------- программы ----------
@app.post("/upload-program")
async def upload_program(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    try:
        content = await file.read()
        data = WorkoutProgram.parse_raw(content)
        prog = WorkoutProgramDB(title=data.title, exercises=json.dumps([ex.dict() for ex in data.exercises], ensure_ascii=False))
        db.add(prog)
        await db.commit()
        await db.refresh(prog)
        return {"id": prog.id, "title": prog.title, "ex_count": len(data.exercises)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Невалидный файл: {e}")

@app.get("/programs")
async def list_programs(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(WorkoutProgramDB))
    return [{"id": p.id, "title": p.title, "ex_count": len(json.loads(p.exercises))} for p in res.scalars()]

@app.get("/programs/{prog_id}", response_model=WorkoutProgram)
async def get_program(prog_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(WorkoutProgramDB).filter(WorkoutProgramDB.id == prog_id))
    row = res.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Программа не найдена")
    return WorkoutProgram(
        id=row.id,
        title=row.title,
        exercises=[Exercise(**ex) for ex in json.loads(row.exercises)]
    )

@app.delete("/programs/{prog_id}")
async def delete_program(prog_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(WorkoutProgramDB).filter(WorkoutProgramDB.id == prog_id))
    row = res.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Программа не найдена")
    await db.delete(row)
    await db.commit()
    return {"ok": True, "deleted_title": row.title}

@app.put("/programs/{prog_id}")
async def update_program(prog_id: int, updated: WorkoutProgram, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(WorkoutProgramDB).filter(WorkoutProgramDB.id == prog_id))
    row = res.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Программа не найдена")
    row.title = updated.title
    row.exercises = json.dumps([ex.dict() for ex in updated.exercises], ensure_ascii=False)
    await db.commit()
    return {"ok": True, "updated_title": row.title}

# ---------- экспорт истории ----------
@app.get("/export-history")
async def export_history(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(FinishedWorkoutDB).order_by(FinishedWorkoutDB.finished_at.desc()))
    items = res.scalars().all()
    if not items:
        raise HTTPException(status_code=404, detail="История пуста")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Дата", "Длительность (сек)", "Упражнения"])
    for w in items:
        writer.writerow([
            w.finished_at.strftime('%d.%m.%Y %H:%M'),
            w.duration_sec,
            "; ".join(json.loads(w.exercises_done))
        ])
    return Response(content=output.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=history.csv"})

# ---------- запуск ----------
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)