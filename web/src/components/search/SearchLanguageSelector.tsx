import { FiGlobe } from "react-icons/fi";

const defaultStyle =
    "rounded-full px-3 py-1.5 font-medium transition-all ";

interface Props {
    setLanguage: (language: string) => void;
    language: string
}

export const SearchLanguageSelector: React.FC<Props> = ({
    setLanguage,
    language
}) => {
    return (
        <div className="inline-flex w-fit items-center rounded-full border border-border bg-background p-1 text-xs shadow-sm">
            <FiGlobe className="ml-2 mr-1 text-subtle" size={14} aria-hidden="true" />
            <button
                type="button"
                className={
                    defaultStyle + `${language === 'english'
                        ? "bg-accent text-white shadow-sm"
                        : "text-default hover:bg-hover hover:text-strong"}`
                }
                onClick={() => {
                    setLanguage('english');
                }}
            >
                <span className="sm:hidden">EN</span>
                <span className="max-sm:hidden">English</span>
            </button>

            <button
                type="button"
                className={
                    defaultStyle +
                    `ml-1 ${language === 'luganda'
                        ? "bg-accent text-white shadow-sm"
                        : "text-default hover:bg-hover hover:text-strong"}`
                }
                onClick={() => {
                    setLanguage('luganda');
                }}
            >
                <span className="sm:hidden">LG</span>
                <span className="max-sm:hidden">Luganda</span>
            </button>
        </div>
    );
};
