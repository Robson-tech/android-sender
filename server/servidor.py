#!/usr/bin/env python3
"""
Servidor Python para receber fotos via socket TCP.

Este script cria um servidor que escuta por conexões TCP em uma porta específica.
Ao receber uma conexão, ele espera receber dados de uma imagem, salva-a em um
diretório local e exibe a imagem mais recente em uma interface gráfica (GUI)
construída com Tkinter.

Funcionalidades:
- Servidor TCP multithread: Capaz de lidar com múltiplas conexões de clientes
  simultaneamente sem travar a interface.
- Interface Gráfica: Mostra o status do servidor, a última foto recebida,
  informações sobre a foto (tamanho, origem) e um botão para parar o servidor.
- Organização de Arquivos: Salva as imagens em um diretório 'data' com
  subpastas organizadas pela data atual (AAAA-MM-DD).
- Protocolo Simples: O cliente deve primeiro enviar 4 bytes indicando o
  tamanho da imagem, seguido pelos dados da imagem em si.

Dependências:
- Pillow: Necessária para manipulação e exibição de imagens na interface.
  O script tenta instalar a biblioteca automaticamente se não for encontrada.
"""

import socket
import threading
import struct
import os
from datetime import datetime
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import io

class PhotoServer:
    """
    Classe que encapsula o servidor de fotos e sua interface gráfica.
    """
    def __init__(self, host='0.0.0.0', port=5001):
        """
        Inicializa o servidor e constrói a interface gráfica.

        Args:
            host (str): O endereço IP no qual o servidor irá escutar.
                        '0.0.0.0' significa que ele escutará em todas as
                        interfaces de rede disponíveis.
            port (int): A porta na qual o servidor irá escutar.
        """
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = False

        # --- Configuração da Interface Gráfica (GUI) ---
        self.root = tk.Tk()
        self.root.title("Servidor de Fotos - Aguardando...")
        self.root.geometry("800x600")
        self.root.configure(bg='#f0f0f0')

        # Frame principal para organizar os widgets
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Label para exibir o status do servidor
        self.status_label = ttk.Label(
            self.main_frame,
            text=f"Servidor aguardando em {host}:{port}...",
            font=('Arial', 12)
        )
        self.status_label.grid(row=0, column=0, columnspan=2, pady=10)

        # Label onde a imagem recebida será exibida
        self.image_label = ttk.Label(self.main_frame, text="Nenhuma foto recebida ainda")
        self.image_label.grid(row=1, column=0, columnspan=2, pady=10)

        # Label para mostrar informações sobre a última foto
        self.info_label = ttk.Label(self.main_frame, text="", font=('Arial', 10))
        self.info_label.grid(row=2, column=0, columnspan=2, pady=5)

        # Botão para parar o servidor e fechar a aplicação
        self.stop_button = ttk.Button(
            self.main_frame,
            text="Parar Servidor",
            command=self.stop_server
        )
        self.stop_button.grid(row=3, column=0, pady=10)

        # Configura o layout para ser redimensionável
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(1, weight=1)

        # Garante que o diretório para salvar as fotos exista
        self.create_data_directory()

    def create_data_directory(self):
        """Cria o diretório 'data/AAAA-MM-DD' para salvar as fotos."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        today = datetime.now().strftime('%Y-%m-%d')
        self.data_dir = os.path.join(base_dir, 'data', today)
        os.makedirs(self.data_dir, exist_ok=True) # exist_ok=True evita erro se a pasta já existir

    def start_server(self):
        """Inicia o servidor em uma thread separada para não bloquear a GUI."""
        self.running = True
        # A thread é configurada como 'daemon' para que seja encerrada
        # automaticamente quando o programa principal (GUI) fechar.
        server_thread = threading.Thread(target=self._run_server, daemon=True)
        server_thread.start()

    def _run_server(self):
        """Contém o loop principal do servidor TCP."""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Permite reutilizar o endereço do socket imediatamente após o fechamento
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5) # Aceita até 5 conexões na fila

            print(f"Servidor iniciado em {self.host}:{self.port}")

            while self.running:
                try:
                    # Aguarda por uma nova conexão
                    client_socket, client_address = self.server_socket.accept()
                    print(f"Cliente conectado: {client_address}")

                    # Cria uma nova thread para lidar com o cliente, permitindo
                    # que o servidor continue aceitando outras conexões.
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, client_address),
                        daemon=True
                    )
                    client_thread.start()

                except OSError:
                    # Ocorre quando o socket é fechado pelo método stop_server
                    if not self.running:
                        print("Servidor foi parado.")
                    else:
                        print("Erro ao aceitar conexão.")
                    break

        except Exception as e:
            print(f"Erro crítico no servidor: {e}")

    def _handle_client(self, client_socket, client_address):
        """
        Processa a comunicação com um cliente conectado.
        O protocolo é: 4 bytes para o tamanho, depois os dados da imagem.
        """
        try:
            # 1. Receber o tamanho da imagem (4 bytes - inteiro big-endian)
            size_data = self._receive_all(client_socket, 4)
            if not size_data:
                return

            # Desempacota os 4 bytes para um inteiro.
            # '>' indica big-endian, 'I' indica unsigned int (4 bytes).
            image_size = struct.unpack('>I', size_data)[0]
            print(f"Tamanho da imagem a ser recebida: {image_size} bytes")

            # 2. Receber os dados da imagem
            image_data = self._receive_all(client_socket, image_size)
            if not image_data:
                return

            # 3. Salvar a imagem e atualizar a GUI
            self._save_and_display_image(image_data, client_address)

            # 4. Enviar confirmação de volta para o cliente
            client_socket.send(b"OK")

        except Exception as e:
            print(f"Erro ao processar cliente {client_address}: {e}")
        finally:
            # Garante que a conexão com o cliente seja sempre fechada
            client_socket.close()

    def _receive_all(self, sock, size):
        """
        Função auxiliar para garantir que exatamente 'size' bytes sejam recebidos do socket.
        `socket.recv()` não garante receber tudo de uma vez.
        """
        data = b''
        while len(data) < size:
            # Pede os bytes restantes
            chunk = sock.recv(size - len(data))
            if not chunk:
                # Conexão foi fechada inesperadamente
                return None
            data += chunk
        return data

    def _save_and_display_image(self, image_data, client_address):
        """Salva a imagem em disco e agenda a atualização da GUI."""
        try:
            # Gera um nome de arquivo com base na hora atual
            timestamp = datetime.now().strftime('%H%M%S')
            filename = f"{timestamp}.jpg"
            filepath = os.path.join(self.data_dir, filename)

            # Salva o arquivo em modo de escrita binária ('wb')
            with open(filepath, 'wb') as f:
                f.write(image_data)
            print(f"Imagem salva: {filepath}")

            # IMPORTANTE: A interface gráfica (Tkinter) só pode ser atualizada
            # pela thread principal. `self.root.after(0, ...)` agenda a
            # execução de `_update_display` na thread principal o mais rápido possível.
            self.root.after(0, self._update_display, image_data, filepath, client_address)

        except Exception as e:
            print(f"Erro ao salvar ou agendar exibição da imagem: {e}")

    def _update_display(self, image_data, filepath, client_address):
        """
        Atualiza a exibição da imagem e os textos na interface.
        Este método é executado SEMPRE pela thread principal da GUI.
        """
        try:
            # Carrega a imagem a partir dos dados em memória
            image = Image.open(io.BytesIO(image_data))

            # Redimensiona a imagem para caber na tela, mantendo a proporção
            display_size = (600, 400)
            image.thumbnail(display_size, Image.Resampling.LANCZOS)

            # Converte a imagem do formato Pillow para o formato Tkinter
            photo = ImageTk.PhotoImage(image)

            # Atualiza o widget da imagem
            self.image_label.configure(image=photo, text="")
            # Mantém uma referência à imagem para evitar que seja coletada pelo garbage collector
            self.image_label.image = photo

            # Atualiza os textos de informação
            file_size = len(image_data)
            info_text = f"Última foto: {os.path.basename(filepath)} | Tamanho: {file_size:,} bytes | De: {client_address[0]}"
            self.info_label.configure(text=info_text)

            # Atualiza o título da janela
            self.root.title(f"Servidor de Fotos - {os.path.basename(filepath)}")

        except Exception as e:
            print(f"Erro ao exibir imagem: {e}")
            self.image_label.configure(image=None, text=f"Erro ao exibir imagem: {e}")

    def stop_server(self):
        """Para o servidor de forma graciosa e fecha a aplicação."""
        print("Parando o servidor...")
        self.running = False
        if self.server_socket:
            # Fechar o socket força a saída do `server_socket.accept()`
            self.server_socket.close()
        # Encerra o loop principal do Tkinter
        self.root.quit()

    def run(self):
        """Executa o servidor e a interface gráfica."""
        try:
            # Inicia o servidor em segundo plano
            self.start_server()

            # Configura o fechamento da janela para chamar self.stop_server
            self.root.protocol("WM_DELETE_WINDOW", self.stop_server)

            # Inicia o loop principal da GUI (bloqueia até a janela ser fechada)
            self.root.mainloop()

        except KeyboardInterrupt:
            # Permite parar o servidor com Ctrl+C no terminal
            self.stop_server()

if __name__ == "__main__":
    # Bloco principal: executado apenas quando o script é rodado diretamente
    
    # Tenta importar Pillow e, se falhar, tenta instalá-la
    try:
        from PIL import Image, ImageTk
    except ImportError:
        print("Biblioteca Pillow não encontrada. Tentando instalar...")
        try:
            os.system("pip install Pillow")
            from PIL import Image, ImageTk
            print("Pillow instalado com sucesso.")
        except Exception as e:
            print(f"Falha ao instalar Pillow: {e}")
            print("Por favor, instale manualmente com: pip install Pillow")
            exit(1)

    # Cria a instância do servidor e inicia a aplicação
    server = PhotoServer()
    server.run()