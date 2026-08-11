package com.williandlima.inclinometro.limits.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(
    entities = [SessionEntity::class, ReadingEntity::class, LimitEventEntity::class],
    version = 1,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun dao(): InclinometerDao

    companion object {
        @Volatile
        private var instance: AppDatabase? = null

        fun getInstance(context: Context): AppDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "inclinometro.db",
                ).build().also { instance = it }
            }
    }
}
