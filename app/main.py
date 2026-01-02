import warnings

# Suppress urllib3 SSL warning that bleeds through TUI
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*urllib3.*")

from app.ui.agent_app import AgentApp


def main():
    AgentApp().run()


if __name__ == "__main__":
    main()