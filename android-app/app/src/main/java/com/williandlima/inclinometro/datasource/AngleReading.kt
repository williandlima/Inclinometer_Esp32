package com.williandlima.inclinometro.datasource

/** Faixa física do eixo de inclinação (-60 a +60 graus). */
const val ANGLE_MIN_DEG = -60.0
const val ANGLE_MAX_DEG = 60.0

/**
 * Limite do azimute (pan). Espelha `PAN_MIN_DEG`/`PAN_MAX_DEG` de
 * `firmware/src/Config.h`: não é a faixa mecânica, é a trava do integrador e o
 * teto do protocolo (int16 × 100 = ±327,67°). A simulação percorre
 * [PAN_SIM_TRAVEL_DEG]; os gráficos partem de [PAN_CHART_DEG].
 */
const val PAN_MIN_DEG = -320.0
const val PAN_MAX_DEG = 320.0
const val PAN_SIM_TRAVEL_DEG = 90.0
const val PAN_CHART_DEG = 95.0

/**
 * Uma leitura dos eixos do inclinômetro.
 *
 * [panDeg] é opcional: fica `null` quando a fonte não fornece azimute — caso
 * de um ESP32 com firmware anterior à v1.2.0, que não expõe a characteristic
 * de pan. Todo o resto do app (limites, histórico, relatório) trata `null`
 * como "este eixo não foi medido" e o ignora, em vez de assumir zero.
 */
data class AngleReading(
    val angleDeg: Double,
    val timestamp: Long, // epoch millis
    val panDeg: Double? = null,
    /**
     * Só preenchido em capturas do Modo Vibração: a velocidade angular bruta
     * do eixo de azimute, como o firmware a envia ([panDeg] é a integral
     * dela). Guardar as duas não é redundância — a análise espectral do
     * azimute precisa da taxa, cujo ruído é branco, enquanto os gráficos e as
     * estatísticas no tempo precisam do ângulo. Ver
     * [com.williandlima.inclinometro.limits.VibrationStatsCalculator.analyzeAxis].
     */
    val panRateDps: Double? = null,
    /**
     * Extremos medidos pelo próprio firmware desde a última calibração/reset,
     * a partir da v1.5.0. Ficam `null` com firmware mais antigo, e aí o app
     * calcula os extremos por conta própria a partir das leituras (ver
     * [com.williandlima.inclinometro.limits.LimitTracker]).
     *
     * Por que o firmware faz isso melhor que o app: ele amostra a 100 Hz,
     * enquanto o notify BLE chega a 5 Hz e ainda traz o valor suavizado para
     * a tela. Uma rajada de vento real de 2° durando meio segundo chegava
     * aqui como 0,78°; medida no firmware, chega como 1,76°. Ver o bloco
     * ANGLE_PEAK_* em `firmware/src/Config.h`.
     */
    val angleMinDeg: Double? = null,
    val angleMaxDeg: Double? = null,
    val panMinDeg: Double? = null,
    val panMaxDeg: Double? = null,
)

enum class ConnectionMode {
    SIMULATED,
    REAL,
}
