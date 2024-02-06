const defaultStyle =
    "py-1 px-2 border rounded border-gray-700 cursor-pointer font-bold ";

interface Props {
    setLanguage: (language: string) => void;
    language: string
}

export const SearchLanguageSelector: React.FC<Props> = ({
    setLanguage,
    language
}) => {
    return (
        <div className="flex text-xs mt-[1.5rem] mb-[1rem]">
            <div
                className={
                    defaultStyle + `bg-white hover:bg-blue-700  border-[1px] hover:text-white ${language === 'english' ? "  " : "border-white bg-blue-700"} `
                }
                onClick={() => {
                    setLanguage('english');
                }}
            >
                English
            </div>

            <div
                className={
                    defaultStyle +
                    `ml-2 bg-white border-[1px] hover:bg-blue-700 hover:text-white  ${language === 'luganda' ? " " : "border-white  bg-blue-700 "}`
                }
                onClick={() => {
                    setLanguage('luganda');
                }}
            >
                Luganda
            </div>
        </div>
    );
};