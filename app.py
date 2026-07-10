"""
Aplicación para limpiar y preparar documentos técnicos PDF para impresión.
Desarrollado para Volaris - Procesamiento de Task Cards y Documentación Técnica.
"""

import streamlit as st
import os
import zipfile
from io import BytesIO
from utils import PDFProcessor
import tempfile
import time

# Configuración de la página
st.set_page_config(
    page_title="Volaris PDF Processor",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título y descripción
st.title("✈️ Volaris - Procesador de Documentación Técnica PDF")
st.markdown("""
Esta aplicación permite limpiar y preparar documentos técnicos PDF para impresión,
eliminando hojas innecesarias y optimizando para impresión a doble cara.
""")

# Sidebar con información
with st.sidebar:
    st.header("📋 Instrucciones")
    st.markdown("""
    1. **Sube los archivos PDF** que deseas procesar
    2. **Selecciona el tipo de procesamiento**
    3. **Haz clic en "Procesar Documentos"**
    4. **Descarga el archivo ZIP** con los resultados
    
    **Características:**
    - Elimina hojas de control y metadatos
    - Añade hojas en blanco para impresión a doble cara
    - Conserva el nombre original + "F"
    """)
    
    st.divider()
    
    st.header("⚙️ Configuración")
    
    # Opciones de procesamiento
    add_blank_pages = st.checkbox(
        "Añadir páginas en blanco (formato doble cara)",
        value=True,
        help="Añade una página en blanco si la tarea termina en página impar"
    )
    
    remove_metadata = st.checkbox(
        "Eliminar páginas de metadatos",
        value=True,
        help="Elimina páginas con metadatos, tablas de control, etc."
    )
    
    st.divider()
    
    st.caption("Version 1.0.0 | Desarrollado para Volaris")

# Área principal
col1, col2 = st.columns([2, 1])

with col1:
    # Uploader de archivos
    uploaded_files = st.file_uploader(
        "📤 Sube tus archivos PDF",
        type=['pdf'],
        accept_multiple_files=True,
        help="Puedes subir uno o varios archivos PDF a la vez"
    )
    
    if uploaded_files:
        st.success(f"✅ {len(uploaded_files)} archivo(s) cargado(s) correctamente")
        
        # Mostrar lista de archivos
        with st.expander("📁 Ver archivos cargados"):
            for file in uploaded_files:
                st.write(f"- {file.name} ({round(file.size/1024, 2)} KB)")

with col2:
    # Botón de procesamiento
    if uploaded_files:
        if st.button("🚀 Procesar Documentos", type="primary", use_container_width=True):
            processor = None
            try:
                with st.spinner("Procesando archivos..."):
                    # Crear instancia del procesador
                    processor = PDFProcessor(
                        add_blank_pages=add_blank_pages,
                        remove_metadata=remove_metadata
                    )
                    
                    # Crear archivo ZIP en memoria
                    zip_buffer = BytesIO()
                    processed_count = 0
                    total_files = len(uploaded_files)
                    
                    # Barra de progreso
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                        for idx, uploaded_file in enumerate(uploaded_files):
                            status_text.text(f"Procesando: {uploaded_file.name} ({idx+1}/{total_files})")
                            
                            # Guardar archivo temporalmente
                            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_input:
                                tmp_input.write(uploaded_file.getvalue())
                                tmp_input_path = tmp_input.name
                            
                            try:
                                # Procesar el PDF
                                output_files = processor.process_pdf(tmp_input_path)
                                
                                # Verificar que se generaron archivos
                                if not output_files:
                                    st.warning(f"⚠️ No se generaron archivos para {uploaded_file.name}")
                                else:
                                    # Añadir archivos procesados al ZIP
                                    for output_file in output_files:
                                        if os.path.exists(output_file):
                                            with open(output_file, 'rb') as f:
                                                zip_file.writestr(
                                                    os.path.basename(output_file),
                                                    f.read()
                                                )
                                            processed_count += 1
                                            
                                    # Limpiar archivos temporales de salida
                                    for output_file in output_files:
                                        try:
                                            if os.path.exists(output_file):
                                                os.remove(output_file)
                                        except:
                                            pass
                                
                            except Exception as e:
                                st.error(f"❌ Error procesando {uploaded_file.name}: {str(e)}")
                            finally:
                                # Limpiar archivo temporal de entrada
                                try:
                                    if os.path.exists(tmp_input_path):
                                        os.remove(tmp_input_path)
                                except:
                                    pass
                            
                            # Actualizar barra de progreso
                            progress_bar.progress((idx + 1) / total_files)
                    
                    # Limpiar archivos temporales residuales
                    if processor:
                        processor.cleanup_temp_files()
                    
                    status_text.text(f"✅ Procesamiento completado: {processed_count} archivos generados")
                    
                    # Preparar descarga
                    if processed_count > 0:
                        zip_buffer.seek(0)
                        st.success(f"🎉 {processed_count} documento(s) procesado(s) exitosamente!")
                        
                        # Botón de descarga
                        st.download_button(
                            label="📥 Descargar ZIP con documentos procesados",
                            data=zip_buffer,
                            file_name="documentos_procesados.zip",
                            mime="application/zip",
                            use_container_width=True
                        )
                        
                        st.balloons()
                    else:
                        st.warning("⚠️ No se generaron documentos. Verifica que los PDFs sean válidos.")
                    
            except Exception as e:
                st.error(f"❌ Error durante el procesamiento: {str(e)}")
                st.exception(e)
                # Limpiar archivos temporales en caso de error
                if processor:
                    processor.cleanup_temp_files()

# Mostrar ejemplo
with st.expander("📖 Ejemplo de uso"):
    st.markdown("""
    **Archivo de entrada:** `N513VL.pdf` (24 páginas)
    **Archivo de salida:** `N513VL F.pdf` (8 páginas)
    
    **Mejoras aplicadas:**
    - Eliminación de hojas de control (W/O Description, ATA, CMR, etc.)
    - Eliminación de páginas con metadatos
    - Eliminación de páginas con solo números
    - Añadida hoja en blanco al final si la tarea termina en página impar
    - Optimización para impresión a doble cara
    """)
    
    st.markdown("### 📋 Tareas identificadas automáticamente:")
    st.markdown("""
    - Task Cards (TASK CARD)
    - Engineering Orders (ENGINEERING ORDER)
    - Daily Checks (DAILY CHECK)
    - Weekly Checks (WEEKLY CHECK)
    """)

# Footer
st.divider()
st.caption("Volaris PDF Processor v1.0.0 | Powered by Streamlit")
