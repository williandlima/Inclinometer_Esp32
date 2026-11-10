package com.williandlima.inclinometro.limits.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(
    entities = [
        SessionEntity::class,
        ReadingEntity::class,
        LimitEventEntity::class,
        VibrationCaptureEntity::class,
        VibrationSampleEntity::class,
    ],
    // v3: colunas do eixo de azimute (pan) em readings e limit_events.
    // v4: azimute também nas amostras do Modo Vibração.
    // v5: tempo programado e versões (app/firmware) em sessions.
    version = 5,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun dao(): InclinometerDao

    companion object {
        @Volatile
        private var instance: AppDatabase? = null

        val MIGRATION_4_5 = object : Migration(4, 5) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE sessions ADD COLUMN plannedDurationS INTEGER")
                db.execSQL("ALTER TABLE sessions ADD COLUMN appVersion TEXT")
                db.execSQL("ALTER TABLE sessions ADD COLUMN firmwareVersion TEXT")
            }
        }

        fun getInstance(context: Context): AppDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "inclinometro.db",
                )
                    // 4 -> 5 preserva o histórico (só acrescenta colunas).
                    // Bancos mais antigos que a v4 ainda são recriados.
                    .addMigrations(MIGRATION_4_5)
                    .fallbackToDestructiveMigration()
                    .build().also { instance = it }
            }
    }
}
