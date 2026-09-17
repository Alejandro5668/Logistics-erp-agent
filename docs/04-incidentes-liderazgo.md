# F-A4 — Gestión de incidentes y liderazgo

## Escenario: tras actualizar el modelo, el agente aprueba ajustes erróneos

### Cómo investigaría la causa raíz

1. **Primero se contiene el daño, después se investiga.** Con el sistema todavía aprobando ajustes incorrectos, lo primero es el rollback (ver abajo), no el diagnóstico.
2. **Revisar el registro detallado de cada ejecución** (ver la estrategia de evaluación en `docs/01-estrategia-llmops.md`), comparando los casos que fallaron contra casos equivalentes de antes de la actualización. La pregunta concreta es: ¿el filtro de seguridad dejó pasar algo que antes bloqueaba, o el agente está llamando mal a la herramienta que calcula el impuesto (con otros argumentos, saltándose el paso, o con un formato de respuesta distinto que rompe algo más adelante en el proceso)?
3. **No asumir que "el modelo nuevo es peor" sin comprobarlo.** Un modelo nuevo puede cambiar su forma de llamar herramientas, su tono, o qué tan literal es con las instrucciones — lo más probable no es que el modelo alucine más, sino que el diseño original dependía, sin que quedara escrito en ningún lado, de un comportamiento específico del modelo anterior.
4. **Correlacionar contra el conjunto de casos de referencia** (el "golden dataset", ver abajo): si ya existía antes del incidente, correrlo contra el modelo nuevo dice de inmediato si el problema es del diseño del agente — y ya se hubiera detectado antes de llegar a producción — o si es algo nuevo, propio de los datos reales.

### Proceso de rollback

1. Volver de inmediato a la versión anterior del modelo. Es la solución más rápida y de menor riesgo, y no requiere entender la causa raíz primero.
2. Si el modelo se selecciona por configuración en vez de estar fijo en el código (como en este proyecto), el rollback es solo cambiar esa configuración, no volver a desplegar nada.
3. Poner en cuarentena manual, sin revertir automáticamente, cualquier ajuste que se haya aprobado solo desde que se activó el modelo nuevo hasta el rollback. Cada uno necesita revisión de una persona, porque ya se confió en una decisión que puede estar mal.

### Golden dataset — para que no se repita

- Un conjunto de casos reales, guardado como parte del proyecto (no en una hoja de cálculo aparte): la pregunta original, qué información se esperaba que el agente consultara, y cuál era la decisión correcta.
- Cada incidente confirmado en producción, como este, se agrega a ese conjunto como un caso permanente que nunca debe volver a fallar. El conjunto crece con el tiempo, no se define una sola vez al principio.
- Se ejecuta automáticamente antes de cualquier cambio de modelo o de instrucciones del agente, no solo cuando alguien se acuerda de correrlo a mano. Un cambio de modelo es exactamente el tipo de evento que debería disparar esta verificación, de la misma forma que un cambio de código dispara la ejecución de tests.
- La exactitud de los montos financieros no admite ningún margen de error en esta verificación — a diferencia de otras métricas de calidad de texto, donde una pequeña variación sí es aceptable.

## Liderazgo técnico: el equipo de frontend reporta 15 a 20 segundos de espera

No se resuelve solo tratando de que el modelo piense más rápido — se resuelve trabajando la percepción de espera y evitando pasos innecesariamente secuenciales:

1. **Mostrar la respuesta a medida que se genera**, en vez de esperar a tenerla completa. El usuario empieza a ver texto en uno o dos segundos en lugar de una pantalla en blanco por 15 o 20. Esto mejora la percepción, no reduce el tiempo real de principio a fin.
2. **Ejecutar en paralelo las consultas que no dependen una de la otra.** Si el agente necesita revisar el ERP y buscar la normativa aplicable para la misma pregunta, no hay ninguna razón para hacerlo en dos pasos separados en vez de al mismo tiempo — esto sí reduce tiempo real.
3. **Mostrar el paso en el que va el agente** ("consultando el ERP", "revisando la normativa") en lugar de silencio hasta tener la respuesta final. Reduce la sensación de espera sin tocar el modelo.
4. **Guardar en caché las búsquedas de normativa más repetidas**, para no tener que rehacer la búsqueda completa cada vez que se pregunta algo similar.
5. **Lo que no propondría:** cambiar a un modelo más chico o más barato solo para ganar velocidad. Eso compromete la precisión en un dominio financiero, y la prueba pide explícitamente no sacrificarla.
