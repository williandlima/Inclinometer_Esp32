package com.williandlima.inclinometro.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.sp

// Fundo azul marinho + detalhes laranja (Avibras Aeroco) — mesma paleta do
// app desktop (ver python-app/ui/main_window.py, constantes NAVY/ORANGE).
private val BrandColors = darkColorScheme(
    primary = Orange,
    onPrimary = Navy,
    secondary = Green,
    background = Navy,
    onBackground = TextLight,
    surface = NavyPanel,
    onSurface = TextLight,
    surfaceVariant = NavyPanel,
    onSurfaceVariant = TextLight,
    error = Red,
    onError = TextLight,
)

private val AppTypography = Typography(
    displayLarge = TextStyle(fontSize = 64.sp),
)

@Composable
fun InclinometroTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = BrandColors,
        typography = AppTypography,
        content = content,
    )
}
