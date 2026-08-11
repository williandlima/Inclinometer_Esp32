package com.williandlima.inclinometro.limits

import com.williandlima.inclinometro.datasource.AngleReading

enum class LimitKind { MIN, MAX }

data class LimitEvent(
    val kind: LimitKind,
    val reading: AngleReading,
)
