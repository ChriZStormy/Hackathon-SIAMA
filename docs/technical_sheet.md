# Ficha Técnica — Reto Hackatón SIAMA (Paso 1)

## Variables objetivo (escala diaria)
- `precipitacion` (mm/día)
- `tmax` (°C)
- `tmin` (°C)

## Principios no negociables
1. **Transparencia absoluta entre dato observado y estimado**:
   - Todo registro diario conserva una bandera explícita de origen (`observado`, `imputado_*`, `abstenido`).
   - Nunca se sobrescribe ni se oculta un dato observado original.
2. **Restricciones físicas estrictas**:
   - Precipitación no negativa: $P \ge 0$.
   - Coherencia térmica diaria: $T_{\max} > T_{\min}$.
3. **Abstención rigurosa**:
   - Cuando un hueco excede el horizonte de soporte estadístico/físico o carece de estaciones vecinas con señal suficiente, el sistema debe abstenerse (`NaN` + bandera `abstenido`) en lugar de fabricar valores sin sustento.
4. **Evaluación sin fuga de datos (No Data Leakage)**:
   - Toda métrica de línea base y modelo debe calcularse sobre observaciones reales enmascaradas cuyo valor original no participa en el ajuste ni en la interpolación.

## Insumos esperados en `data/raw/`
- `estaciones.csv`
- `series_diarias.csv`
- `covariables.gpkg`
- `test_publico.csv`
