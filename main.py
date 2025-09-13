# backend/main.py
from fastapi import FastAPI, HTTPException, UploadFile, File, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import uvicorn
import os
import json
import csv
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, DateTime, Float, select
from sqlalchemy.ext.declarative import declarative_base
import aiosqlite

# Исправленный CORS - разрешаем все origins для тестирования
app = FastAPI(title="FitTracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Разрешаем все origins для тестирования
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Модели Pydantic
class Exercise(BaseModel):
    id: int
    name: str
    tip: str | None = None
    yt_search: str | None = None
    sets: int = 1
    reps: int = 1
    weight: float = 0.0

class WorkoutProgram(BaseModel):
    id: int | None = None
    title: str
    exercises: list[Exercise]

class FinishedWorkout(BaseModel):
    id: int
    finished_at: datetime
    duration_sec: int
    exercises_done: list[str]

# Модели SQLAlchemy
Base = declarative_base()

class ExerciseDB(Base):
    __tablename__ = "exercises"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    tip = Column(String, nullable=True)
    yt_search = Column(String, nullable=True)
    sets = Column(Integer, default=1)
    reps = Column(Integer, default=1)
    weight = Column(Float, default=0.0)

class WorkoutProgramDB(Base):
    __tablename__ = "programs"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)

class FinishedWorkoutDB(Base):
    __tablename__ = "workouts"
    
    id = Column(Integer, primary_key=True, index=True)
    finished_at = Column(DateTime)
    duration_sec = Column(Integer)
    exercises_done = Column(String)  # Сохраняем как строку, разделенную запятыми

# Настройка базы данных
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./fittracker.db")
engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Создание таблиц
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Заполнение начальными данными, если таблица пуста
    async with async_session() as session:
        result = await session.execute(select(ExerciseDB))
        exercises = result.scalars().all()
        
        if not exercises:
            # Добавляем начальные упражнения
            initial_exercises = [
                ExerciseDB(id=1, name="Жим лёжа", tip="Не забывай про разминку!", yt_search="bench press tutorial"),
                ExerciseDB(id=2, name="Приседания", tip="Следи за спиной", yt_search="squats tutorial"),
                ExerciseDB(id=3, name="Становая тяга", tip="Разгибай ноги", yt_search="deadlift tutorial"),
                ExerciseDB(id=4, name="Подтягивания", tip="Не раскачивайся", yt_search="pull ups tutorial"),
                ExerciseDB(id=5, name="Отжимания", tip="Держи тело прямо", yt_search="push ups tutorial"),
                ExerciseDB(id=6, name="Планка", tip="Не прогибай поясницу", yt_search="plank tutorial"),
            ]
            
            session.add_all(initial_exercises)
            await session.commit()

# Эндпоинты API
@app.get("/")
async def root():
    return {"message": "Сервер работает!"}

@app.get("/exercises")
async def get_exercises():
    async with async_session() as session:
        result = await session.execute(select(ExerciseDB))
        exercises = result.scalars().all()
        
        return [
            Exercise(
                id=ex.id,
                name=ex.name,
                tip=ex.tip,
                yt_search=ex.yt_search,
                sets=ex.sets,
                reps=ex.reps,
                weight=ex.weight
            ) 
            for ex in exercises
        ]

@app.post("/upload-program")
async def upload_program(file: UploadFile = File(...)):
    try:
        content = await file.read()
        # Парсим JSON напрямую
        program_data = json.loads(content)
        
        # Валидируем через Pydantic
        program = WorkoutProgram(**program_data)
        
        return {"message": f"Программа '{program.title}' успешно загружена", "program": program}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка загрузки: {str(e)}")

@app.get("/programs")
async def list_programs():
    # Возвращаем пустой список или можно добавить логику для сохраненных программ
    return []

@app.delete("/programs/{program_id}")
async def delete_program(program_id: int):
    return {"message": f"Программа {program_id} удалена"}

@app.put("/programs/{program_id}")
async def update_program(program_id: int, program: WorkoutProgram):
    return {"message": f"Программа {program_id} обновлена", "program": program}

@app.get("/export-history")
async def export_history():
    # Возвращаем пустой CSV или можно добавить логику экспорта
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Дата", "Длительность (сек)", "Упражнения"])
    return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=history.csv"})

# Исправленный запуск сервера
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)